using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

static class TabDeckLauncher {
    [STAThread]
    static void Main(string[] args) {
        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        string pyw = Path.Combine(baseDir, ".venv", "Scripts", "pythonw.exe");
        string entry = Path.Combine(baseDir, "app", "tray.py");
        string reqs = Path.Combine(baseDir, "requirements.txt");

        if (!File.Exists(entry)) {
            MessageBox.Show(
                "TabDeck backend (app\\tray.py) was not found in:\n" + baseDir,
                "TabDeck",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return;
        }

        // First-time automatic bootstrap: create .venv and install requirements with zero manual CLI work
        if (!File.Exists(pyw)) {
            DialogResult ok = MessageBox.Show(
                "Welcome to TabDeck!\n\nFirst-time setup will create a local Python environment and install TabDeck's dependencies automatically (takes ~30 seconds).\n\nContinue?",
                "TabDeck — First-Time Setup",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Information
            );
            if (ok != DialogResult.Yes) return;

            string setupCmd = "/c title TabDeck First-Time Setup && echo Setting up TabDeck... && " +
                              "python -m venv .venv && .venv\\Scripts\\python.exe -m pip install --upgrade pip && " +
                              ".venv\\Scripts\\pip.exe install -r \"" + reqs + "\"";
            var setupPsi = new ProcessStartInfo {
                FileName = "cmd.exe",
                Arguments = setupCmd,
                WorkingDirectory = baseDir,
                UseShellExecute = true,
            };
            try {
                Process p = Process.Start(setupPsi);
                if (p != null) p.WaitForExit();
            } catch (Exception ex) {
                MessageBox.Show(
                    "First-time setup failed. Make sure Python 3.11+ is installed and on PATH.\n\n" + ex.Message,
                    "TabDeck Setup",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
                return;
            }

            if (!File.Exists(pyw)) {
                MessageBox.Show(
                    "Setup did not finish creating .venv. Please ensure Python 3.11+ is installed from python.org and try again.",
                    "TabDeck Setup",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning
                );
                return;
            }
        }

        var psi = new ProcessStartInfo {
            FileName = pyw,
            Arguments = "\"" + entry + "\"",
            WorkingDirectory = baseDir,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        try {
            Process.Start(psi);
        } catch (Exception ex) {
            MessageBox.Show(
                "Could not start TabDeck:\n" + ex.Message,
                "TabDeck",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
        }
    }
}
