/*
 * tabdeck_mc.c — Dual-Mode Android Multi Control Receiver for TabDeck
 *
 * Supports BOTH:
 *   1. Rooted Android (/dev/uinput) — runs persistently via Magisk service.d
 *   2. UNROOTED Android (/dev/uhid) — runs as standard `adb shell` (uid=2000,
 *      group `uhid`) on stock Android 11-15+ devices (e.g. Samsung Galaxy S24)
 *      via USB or Wireless Debugging, with ZERO root required!
 *
 * Protocol (TCP port 8767, 8-byte fixed binary frames):
 *   byte 0:    ev_type  (0=SYN, 1=EV_KEY, 2=EV_REL, 9=RELEASE_ALL, 10=PING)
 *   byte 1..2: uint16_le code (Linux input-event-codes.h)
 *   byte 3:    reserved
 *   byte 4..7: int32_le value
 */
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <linux/uhid.h>
#include <linux/uinput.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

#define LISTEN_PORT 8767
#define MAX_HELD 256

static volatile int g_running = 1;
static int g_use_uhid = 0;
static int g_fd = -1;

/* Track held keys/buttons so disconnect or RELEASE_ALL never leaves stuck keys */
static uint8_t g_held_keys[MAX_HELD];
static uint8_t g_held_btns[8];

/* Pending HID mouse deltas flushed on SYN_REPORT */
static int32_t g_pend_dx = 0;
static int32_t g_pend_dy = 0;
static int32_t g_pend_wheel = 0;
static int32_t g_pend_hwheel = 0;
static int g_mouse_dirty = 0;
static int g_kbd_dirty = 0;
static int g_cons_dirty = 0;
static uint16_t g_cons_usage = 0;

/*
 * Composite USB HID Report Descriptor:
 *   Report ID 1: Mouse (5 buttons + X/Y 16-bit relative + V-Wheel + H-Wheel)
 *   Report ID 2: Keyboard (8 modifier bits + 1 reserved + 6 boot key slots)
 *   Report ID 3: Consumer Control (Mute, Vol Up/Down, Play/Pause, Next/Prev, Home, Back)
 */
static const uint8_t HID_RDESC[] = {
    /* ---- Report ID 1: Mouse ---- */
    0x05, 0x01,       /* Usage Page (Generic Desktop) */
    0x09, 0x02,       /* Usage (Mouse) */
    0xA1, 0x01,       /* Collection (Application) */
    0x85, 0x01,       /*   Report ID (1) */
    0x09, 0x01,       /*   Usage (Pointer) */
    0xA1, 0x00,       /*   Collection (Physical) */
    0x05, 0x09,       /*     Usage Page (Button) */
    0x19, 0x01,       /*     Usage Minimum (Button 1) */
    0x29, 0x05,       /*     Usage Maximum (Button 5) */
    0x15, 0x00,       /*     Logical Minimum (0) */
    0x25, 0x01,       /*     Logical Maximum (1) */
    0x95, 0x05,       /*     Report Count (5) */
    0x75, 0x01,       /*     Report Size (1) */
    0x81, 0x02,       /*     Input (Data, Variable, Absolute) */
    0x95, 0x01,       /*     Report Count (1) */
    0x75, 0x03,       /*     Report Size (3) */
    0x81, 0x03,       /*     Input (Constant) — 3 padding bits */
    0x05, 0x01,       /*     Usage Page (Generic Desktop) */
    0x09, 0x30,       /*     Usage (X) */
    0x09, 0x31,       /*     Usage (Y) */
    0x16, 0x00, 0x80, /*     Logical Minimum (-32768) */
    0x26, 0xFF, 0x7F, /*     Logical Maximum (32767) */
    0x75, 0x10,       /*     Report Size (16) */
    0x95, 0x02,       /*     Report Count (2) */
    0x81, 0x06,       /*     Input (Data, Variable, Relative) */
    0x09, 0x38,       /*     Usage (Wheel) */
    0x15, 0x81,       /*     Logical Minimum (-127) */
    0x25, 0x7F,       /*     Logical Maximum (127) */
    0x75, 0x08,       /*     Report Size (8) */
    0x95, 0x01,       /*     Report Count (1) */
    0x81, 0x06,       /*     Input (Data, Variable, Relative) */
    0x05, 0x0C,       /*     Usage Page (Consumer) */
    0x0A, 0x38, 0x02, /*     Usage (AC Pan / H-Wheel) */
    0x15, 0x81,       /*     Logical Minimum (-127) */
    0x25, 0x7F,       /*     Logical Maximum (127) */
    0x75, 0x08,       /*     Report Size (8) */
    0x95, 0x01,       /*     Report Count (1) */
    0x81, 0x06,       /*     Input (Data, Variable, Relative) */
    0xC0,             /*   End Collection */
    0xC0,             /* End Collection */

    /* ---- Report ID 2: Keyboard ---- */
    0x05, 0x01,       /* Usage Page (Generic Desktop) */
    0x09, 0x06,       /* Usage (Keyboard) */
    0xA1, 0x01,       /* Collection (Application) */
    0x85, 0x02,       /*   Report ID (2) */
    0x05, 0x07,       /*   Usage Page (Keyboard/Keypad) */
    0x19, 0xE0,       /*   Usage Minimum (Left Control) */
    0x29, 0xE7,       /*   Usage Maximum (Right GUI) */
    0x15, 0x00,       /*   Logical Minimum (0) */
    0x25, 0x01,       /*   Logical Maximum (1) */
    0x75, 0x01,       /*   Report Size (1) */
    0x95, 0x08,       /*   Report Count (8) */
    0x81, 0x02,       /*   Input (Data, Variable, Absolute) */
    0x95, 0x01,       /*   Report Count (1) */
    0x75, 0x08,       /*   Report Size (8) */
    0x81, 0x03,       /*   Input (Constant) */
    0x95, 0x06,       /*   Report Count (6) */
    0x75, 0x08,       /*   Report Size (8) */
    0x15, 0x00,       /*   Logical Minimum (0) */
    0x25, 0xE7,       /*   Logical Maximum (231) */
    0x05, 0x07,       /*   Usage Page (Keyboard/Keypad) */
    0x19, 0x00,       /*   Usage Minimum (0) */
    0x29, 0xE7,       /*   Usage Maximum (231) */
    0x81, 0x00,       /*   Input (Data, Array) */
    0xC0,             /* End Collection */

    /* ---- Report ID 3: Consumer Media Keys ---- */
    0x05, 0x0C,       /* Usage Page (Consumer) */
    0x09, 0x01,       /* Usage (Consumer Control) */
    0xA1, 0x01,       /* Collection (Application) */
    0x85, 0x03,       /*   Report ID (3) */
    0x15, 0x00,       /*   Logical Minimum (0) */
    0x26, 0xFF, 0x03, /*   Logical Maximum (1023) */
    0x19, 0x00,       /*   Usage Minimum (0) */
    0x2A, 0xFF, 0x03, /*   Usage Maximum (1023) */
    0x75, 0x10,       /*   Report Size (16) */
    0x95, 0x01,       /*   Report Count (1) */
    0x81, 0x00,       /*   Input (Data, Array) */
    0xC0              /* End Collection */
};

/* Linux KEY_* -> USB HID Usage ID (Page 0x07) */
static uint8_t linux_key_to_hid(uint16_t k) {
    switch (k) {
        case 1: return 0x29;   /* ESC */
        case 2: return 0x1E;   /* 1 */
        case 3: return 0x1F;   /* 2 */
        case 4: return 0x20;   /* 3 */
        case 5: return 0x21;   /* 4 */
        case 6: return 0x22;   /* 5 */
        case 7: return 0x23;   /* 6 */
        case 8: return 0x24;   /* 7 */
        case 9: return 0x25;   /* 8 */
        case 10: return 0x26;  /* 9 */
        case 11: return 0x27;  /* 0 */
        case 12: return 0x2D;  /* - */
        case 13: return 0x2E;  /* = */
        case 14: return 0x2A;  /* Backspace */
        case 15: return 0x2B;  /* Tab */
        case 16: return 0x14;  /* Q */
        case 17: return 0x1A;  /* W */
        case 18: return 0x08;  /* E */
        case 19: return 0x15;  /* R */
        case 20: return 0x17;  /* T */
        case 21: return 0x1C;  /* Y */
        case 22: return 0x18;  /* U */
        case 23: return 0x0C;  /* I */
        case 24: return 0x12;  /* O */
        case 25: return 0x13;  /* P */
        case 26: return 0x2F;  /* [ */
        case 27: return 0x30;  /* ] */
        case 28: return 0x28;  /* Enter */
        case 30: return 0x04;  /* A */
        case 31: return 0x16;  /* S */
        case 32: return 0x07;  /* D */
        case 33: return 0x09;  /* F */
        case 34: return 0x0A;  /* G */
        case 35: return 0x0B;  /* H */
        case 36: return 0x0D;  /* J */
        case 37: return 0x0E;  /* K */
        case 38: return 0x0F;  /* L */
        case 39: return 0x33;  /* ; */
        case 40: return 0x34;  /* ' */
        case 41: return 0x35;  /* ` */
        case 43: return 0x31;  /* \ */
        case 44: return 0x1D;  /* Z */
        case 45: return 0x1B;  /* X */
        case 46: return 0x06;  /* C */
        case 47: return 0x19;  /* V */
        case 48: return 0x05;  /* B */
        case 49: return 0x11;  /* N */
        case 50: return 0x10;  /* M */
        case 51: return 0x36;  /* , */
        case 52: return 0x37;  /* . */
        case 53: return 0x38;  /* / */
        case 55: return 0x55;  /* KP * */
        case 57: return 0x2C;  /* Space */
        case 58: return 0x39;  /* CapsLock */
        case 59: return 0x3A;  /* F1 */
        case 60: return 0x3B;  /* F2 */
        case 61: return 0x3C;  /* F3 */
        case 62: return 0x3D;  /* F4 */
        case 63: return 0x3E;  /* F5 */
        case 64: return 0x3F;  /* F6 */
        case 65: return 0x40;  /* F7 */
        case 66: return 0x41;  /* F8 */
        case 67: return 0x42;  /* F9 */
        case 68: return 0x43;  /* F10 */
        case 69: return 0x53;  /* NumLock */
        case 71: return 0x5F;  /* KP 7 */
        case 72: return 0x60;  /* KP 8 */
        case 73: return 0x61;  /* KP 9 */
        case 74: return 0x56;  /* KP - */
        case 75: return 0x5C;  /* KP 4 */
        case 76: return 0x5D;  /* KP 5 */
        case 77: return 0x5E;  /* KP 6 */
        case 78: return 0x57;  /* KP + */
        case 79: return 0x59;  /* KP 1 */
        case 80: return 0x5A;  /* KP 2 */
        case 81: return 0x5B;  /* KP 3 */
        case 82: return 0x62;  /* KP 0 */
        case 83: return 0x63;  /* KP . */
        case 87: return 0x44;  /* F11 */
        case 88: return 0x45;  /* F12 */
        case 98: return 0x54;  /* KP / */
        case 102: return 0x4A; /* Home */
        case 103: return 0x52; /* Up */
        case 104: return 0x4B; /* PageUp */
        case 105: return 0x50; /* Left */
        case 106: return 0x4F; /* Right */
        case 107: return 0x4D; /* End */
        case 108: return 0x51; /* Down */
        case 109: return 0x4E; /* PageDown */
        case 110: return 0x49; /* Insert */
        case 111: return 0x4C; /* Delete */
        default: return 0;
    }
}

static uint8_t linux_key_to_modbit(uint16_t k) {
    switch (k) {
        case 29:  return 0x01; /* LCtrl */
        case 42:  return 0x02; /* LShift */
        case 56:  return 0x04; /* LAlt */
        case 125: return 0x08; /* LMeta/Win */
        case 97:  return 0x10; /* RCtrl */
        case 54:  return 0x20; /* RShift */
        case 100: return 0x40; /* RAlt */
        case 126: return 0x80; /* RMeta/Win */
        default:  return 0;
    }
}

static uint16_t linux_key_to_consumer(uint16_t k) {
    switch (k) {
        case 113: return 0x00E2; /* Mute */
        case 114: return 0x00EA; /* Vol Down */
        case 115: return 0x00E9; /* Vol Up */
        case 163: return 0x00B5; /* Next Track */
        case 164: return 0x00CD; /* Play/Pause */
        case 165: return 0x00B6; /* Prev Track */
        default:  return 0;
    }
}

static void on_sig(int sig) {
    (void)sig;
    g_running = 0;
}

/* ---- UINPUT helpers ---- */
static void uinput_emit(uint16_t type, uint16_t code, int32_t value) {
    if (g_fd < 0) return;
    struct input_event ev;
    memset(&ev, 0, sizeof(ev));
    gettimeofday(&ev.time, NULL);
    ev.type = type;
    ev.code = code;
    ev.value = value;
    (void)write(g_fd, &ev, sizeof(ev));
}

/* ---- UHID helpers ---- */
static void uhid_send_report(const uint8_t *data, uint16_t size) {
    if (g_fd < 0) return;
    struct uhid_event ev;
    memset(&ev, 0, sizeof(ev));
    ev.type = UHID_INPUT2;
    ev.u.input2.size = size;
    memcpy(ev.u.input2.data, data, size);
    (void)write(g_fd, &ev, sizeof(ev));
}

static void uhid_flush(void) {
    if (g_mouse_dirty) {
        uint8_t btns = 0;
        for (int i = 0; i < 5; i++) {
            if (g_held_btns[i]) btns |= (uint8_t)(1u << i);
        }
        int16_t dx = (int16_t)(g_pend_dx > 32767 ? 32767 : (g_pend_dx < -32768 ? -32768 : g_pend_dx));
        int16_t dy = (int16_t)(g_pend_dy > 32767 ? 32767 : (g_pend_dy < -32768 ? -32768 : g_pend_dy));
        int8_t wh = (int8_t)(g_pend_wheel > 127 ? 127 : (g_pend_wheel < -127 ? -127 : g_pend_wheel));
        int8_t hw = (int8_t)(g_pend_hwheel > 127 ? 127 : (g_pend_hwheel < -127 ? -127 : g_pend_hwheel));
        uint8_t rep[8];
        rep[0] = 1; /* Report ID 1: Mouse */
        rep[1] = btns;
        rep[2] = (uint8_t)(dx & 0xFF);
        rep[3] = (uint8_t)((dx >> 8) & 0xFF);
        rep[4] = (uint8_t)(dy & 0xFF);
        rep[5] = (uint8_t)((dy >> 8) & 0xFF);
        rep[6] = (uint8_t)wh;
        rep[7] = (uint8_t)hw;
        uhid_send_report(rep, sizeof(rep));
        g_pend_dx = g_pend_dy = g_pend_wheel = g_pend_hwheel = 0;
        g_mouse_dirty = 0;
    }

    if (g_kbd_dirty) {
        uint8_t rep[9];
        memset(rep, 0, sizeof(rep));
        rep[0] = 2; /* Report ID 2: Keyboard */
        uint8_t mods = 0;
        int slot = 0;
        for (int k = 1; k < MAX_HELD; k++) {
            if (!g_held_keys[k]) continue;
            uint8_t mb = linux_key_to_modbit((uint16_t)k);
            if (mb) {
                mods |= mb;
            } else if (slot < 6) {
                uint8_t hid = linux_key_to_hid((uint16_t)k);
                if (hid) rep[3 + slot++] = hid;
            }
        }
        rep[1] = mods;
        uhid_send_report(rep, sizeof(rep));
        g_kbd_dirty = 0;
    }

    if (g_cons_dirty) {
        uint8_t rep[3];
        rep[0] = 3; /* Report ID 3: Consumer */
        rep[1] = (uint8_t)(g_cons_usage & 0xFF);
        rep[2] = (uint8_t)((g_cons_usage >> 8) & 0xFF);
        uhid_send_report(rep, sizeof(rep));
        g_cons_dirty = 0;
    }
}

static void release_all_held(void) {
    if (!g_use_uhid) {
        int changed = 0;
        for (int i = 0; i < MAX_HELD; i++) {
            if (g_held_keys[i]) {
                uinput_emit(EV_KEY, (uint16_t)i, 0);
                g_held_keys[i] = 0;
                changed = 1;
            }
        }
        for (int i = 0; i < 8; i++) {
            if (g_held_btns[i]) {
                uinput_emit(EV_KEY, (uint16_t)(BTN_LEFT + i), 0);
                g_held_btns[i] = 0;
                changed = 1;
            }
        }
        if (changed) uinput_emit(EV_SYN, SYN_REPORT, 0);
        return;
    }

    memset(g_held_keys, 0, sizeof(g_held_keys));
    memset(g_held_btns, 0, sizeof(g_held_btns));
    g_pend_dx = g_pend_dy = g_pend_wheel = g_pend_hwheel = 0;
    g_cons_usage = 0;
    g_mouse_dirty = g_kbd_dirty = g_cons_dirty = 1;
    uhid_flush();
}

static int setup_uinput(void) {
    int fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
    if (fd < 0) return -1;

    ioctl(fd, UI_SET_EVBIT, EV_KEY);
    ioctl(fd, UI_SET_EVBIT, EV_REL);
    ioctl(fd, UI_SET_EVBIT, EV_SYN);

    ioctl(fd, UI_SET_RELBIT, REL_X);
    ioctl(fd, UI_SET_RELBIT, REL_Y);
    ioctl(fd, UI_SET_RELBIT, REL_WHEEL);
    ioctl(fd, UI_SET_RELBIT, REL_HWHEEL);

    ioctl(fd, UI_SET_KEYBIT, BTN_LEFT);
    ioctl(fd, UI_SET_KEYBIT, BTN_RIGHT);
    ioctl(fd, UI_SET_KEYBIT, BTN_MIDDLE);
    ioctl(fd, UI_SET_KEYBIT, BTN_SIDE);
    ioctl(fd, UI_SET_KEYBIT, BTN_EXTRA);

    for (int k = 1; k <= 248; k++) {
        ioctl(fd, UI_SET_KEYBIT, k);
    }

    struct uinput_setup usetup;
    memset(&usetup, 0, sizeof(usetup));
    usetup.id.bustype = BUS_USB;
    usetup.id.vendor = 0x18D1;
    usetup.id.product = 0x5444;
    usetup.id.version = 1;
    strncpy(usetup.name, "TabDeck Multi Control", UINPUT_MAX_NAME_SIZE - 1);

    if (ioctl(fd, UI_DEV_SETUP, &usetup) < 0) {
        struct uinput_user_dev udev;
        memset(&udev, 0, sizeof(udev));
        udev.id = usetup.id;
        strncpy(udev.name, "TabDeck Multi Control", UINPUT_MAX_NAME_SIZE - 1);
        if (write(fd, &udev, sizeof(udev)) < 0) {
            close(fd);
            return -1;
        }
    }
    if (ioctl(fd, UI_DEV_CREATE) < 0) {
        close(fd);
        return -1;
    }
    return fd;
}

static int setup_uhid(void) {
    int fd = open("/dev/uhid", O_RDWR | O_NONBLOCK);
    if (fd < 0) {
        perror("open /dev/uhid");
        return -1;
    }
    struct uhid_event ev;
    memset(&ev, 0, sizeof(ev));
    ev.type = UHID_CREATE2;
    strncpy((char *)ev.u.create2.name, "TabDeck Multi Control", sizeof(ev.u.create2.name) - 1);
    ev.u.create2.rd_size = (uint16_t)sizeof(HID_RDESC);
    memcpy(ev.u.create2.rd_data, HID_RDESC, sizeof(HID_RDESC));
    ev.u.create2.bus = BUS_USB;
    ev.u.create2.vendor = 0x18D1;
    ev.u.create2.product = 0x5445;
    ev.u.create2.version = 1;
    ev.u.create2.country = 0;

    if (write(fd, &ev, sizeof(ev)) < 0) {
        perror("UHID_CREATE2");
        close(fd);
        return -1;
    }
    return fd;
}

static int read_exact(int fd, uint8_t *buf, size_t n) {
    size_t got = 0;
    while (got < n) {
        ssize_t r = recv(fd, buf + got, n - got, 0);
        if (r <= 0) {
            if (r < 0 && errno == EINTR) continue;
            return -1;
        }
        got += (size_t)r;
    }
    return 0;
}

static void handle_client(int sfd, int cfd) {
    int one = 1;
    setsockopt(cfd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));

    uint8_t pkt[8];
    while (g_running) {
        fd_set rfds;
        FD_ZERO(&rfds);
        FD_SET(sfd, &rfds);
        FD_SET(cfd, &rfds);
        int maxfd = (sfd > cfd ? sfd : cfd) + 1;
        int sel = select(maxfd, &rfds, NULL, NULL, NULL);
        if (sel < 0) {
            if (errno == EINTR) continue;
            break;
        }
        /* Preempt stale client immediately if a new laptop connection arrives */
        if (FD_ISSET(sfd, &rfds)) {
            break;
        }
        if (!FD_ISSET(cfd, &rfds)) continue;
        if (read_exact(cfd, pkt, 8) != 0) break;
        uint8_t ev_type = pkt[0];
        uint16_t code = (uint16_t)pkt[1] | ((uint16_t)pkt[2] << 8);
        int32_t val = (int32_t)((uint32_t)pkt[4]
                              | ((uint32_t)pkt[5] << 8)
                              | ((uint32_t)pkt[6] << 16)
                              | ((uint32_t)pkt[7] << 24));

        if (ev_type == 9) {
            release_all_held();
            continue;
        }
        if (ev_type == 10) {
            const uint8_t pong[4] = {'P', 'O', 'N', 'G'};
            (void)send(cfd, pong, 4, MSG_NOSIGNAL);
            continue;
        }

        if (!g_use_uhid) {
            if (ev_type == EV_KEY) {
                if (code < MAX_HELD) g_held_keys[code] = (val != 0) ? 1 : 0;
                else if (code >= BTN_LEFT && code < BTN_LEFT + 8) g_held_btns[code - BTN_LEFT] = (val != 0) ? 1 : 0;
                uinput_emit(EV_KEY, code, val);
            } else if (ev_type == EV_REL) {
                uinput_emit(EV_REL, code, val);
            } else if (ev_type == EV_SYN) {
                uinput_emit(EV_SYN, SYN_REPORT, 0);
            }
        } else {
            if (ev_type == EV_KEY) {
                if (code >= BTN_LEFT && code < BTN_LEFT + 8) {
                    g_held_btns[code - BTN_LEFT] = (val != 0) ? 1 : 0;
                    g_mouse_dirty = 1;
                } else if (code < MAX_HELD) {
                    uint16_t cu = linux_key_to_consumer(code);
                    if (cu) {
                        g_cons_usage = (val != 0) ? cu : 0;
                        g_cons_dirty = 1;
                    } else {
                        g_held_keys[code] = (val != 0) ? 1 : 0;
                        g_kbd_dirty = 1;
                    }
                }
            } else if (ev_type == EV_REL) {
                if (code == REL_X) g_pend_dx += val;
                else if (code == REL_Y) g_pend_dy += val;
                else if (code == REL_WHEEL) g_pend_wheel += val;
                else if (code == REL_HWHEEL) g_pend_hwheel += val;
                g_mouse_dirty = 1;
            } else if (ev_type == EV_SYN) {
                uhid_flush();
            }
        }
    }

    release_all_held();
}

int main(int argc, char **argv) {
    signal(SIGINT, on_sig);
    signal(SIGTERM, on_sig);
    signal(SIGPIPE, SIG_IGN);

    int force_uhid = 0;
    int run_daemon = 0;
    int port = LISTEN_PORT;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--uhid") == 0) force_uhid = 1;
        else if (strcmp(argv[i], "--daemon") == 0) run_daemon = 1;
        else if (strcmp(argv[i], "--port") == 0 && i + 1 < argc) port = atoi(argv[++i]);
    }

    if (!force_uhid) {
        g_fd = setup_uinput();
        if (g_fd >= 0) {
            g_use_uhid = 0;
        }
    }
    if (g_fd < 0) {
        g_fd = setup_uhid();
        if (g_fd >= 0) {
            g_use_uhid = 1;
        }
    }
    if (g_fd < 0) {
        fprintf(stderr, "Failed to open /dev/uinput or /dev/uhid\n");
        return 1;
    }

    int sfd = socket(AF_INET, SOCK_STREAM, 0);
    if (sfd < 0) {
        perror("socket");
        return 1;
    }
    int one = 1;
    setsockopt(sfd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons((uint16_t)port);

    if (bind(sfd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("bind");
        close(sfd);
        return 1;
    }
    if (listen(sfd, 4) < 0) {
        perror("listen");
        close(sfd);
        return 1;
    }

    fprintf(stdout, "TabDeck Multi Control (%s mode) listening on :%d\n",
            g_use_uhid ? "non-root UHID" : "root uinput", port);
    fflush(stdout);

    if (run_daemon) {
        if (daemon(0, 0) < 0) {
            perror("daemon");
        }
    }

    while (g_running) {
        int cfd = accept(sfd, NULL, NULL);
        if (cfd < 0) {
            if (errno == EINTR) continue;
            usleep(100000);
            continue;
        }
        handle_client(sfd, cfd);
        close(cfd);
    }

    close(sfd);
    if (g_use_uhid) {
        struct uhid_event ev;
        memset(&ev, 0, sizeof(ev));
        ev.type = UHID_DESTROY;
        (void)write(g_fd, &ev, sizeof(ev));
    } else {
        ioctl(g_fd, UI_DEV_DESTROY);
    }
    close(g_fd);
    return 0;
}
