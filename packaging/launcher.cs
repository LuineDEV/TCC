using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class MailDeskLauncher
{
    [STAThread]
    private static int Main(string[] args)
    {
        bool smokeTest = Array.IndexOf(args, "--smoke-test") >= 0;
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string runtime = Path.Combine(root, "_internal");
        string entry = Path.Combine(runtime, "demo_windows.py");
        try
        {
            var start = new ProcessStartInfo {
                FileName = Path.Combine(runtime, "pythonw.exe"),
                Arguments = "\"" + entry + "\"" + (smokeTest ? " --smoke-test" : ""),
                WorkingDirectory = root,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            start.EnvironmentVariables["NLTK_DATA"] = Path.Combine(runtime, "nltk_data");
            using (Process child = Process.Start(start))
            {
                if (!smokeTest) return 0;
                child.WaitForExit();
                return child.ExitCode;
            }
        }
        catch (Exception error)
        {
            if (smokeTest)
                File.WriteAllText(Path.Combine(root, "maildesk-smoke-error.txt"), error.Message);
            else
                MessageBox.Show("Extraia todo o ZIP antes de abrir o Mail Desk.\n\n" + error.Message,
                                "Mail Desk", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
