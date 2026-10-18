"""Portable static checks. Native WinForms needs actual Windows for UI execution."""
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class WindowsClientContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.launch = (HERE / 'neon-client.ps1').read_text(encoding='utf-8')
        cls.browser = (HERE / 'neon-browser.ps1').read_text(encoding='utf-8')
        cls.bat = (HERE / 'neon-browse.bat').read_text(encoding='utf-8')

    def test_native_default_preserves_opera_option(self):
        self.assertIn('[switch]$Opera', self.launch)
        self.assertIn("if (-not $Opera)", self.launch)
        self.assertIn("& $browser", self.launch)
        self.assertIn("$link.Arguments = '-Opera'", self.launch)
        self.assertIn('Start-Process -FilePath $opera', self.launch)

    def test_no_additional_windows_dependencies(self):
        self.assertIn('System.Windows.Forms', self.browser)
        self.assertIn('System.Drawing', self.browser)
        self.assertIn('Import-Clixml', self.browser)
        self.assertIn('Invoke-RestMethod', self.browser)
        self.assertNotIn('pip install', self.browser)
        self.assertNotIn('Invoke-Expression', self.browser)

    def test_explorer_uses_authenticated_server_apis(self):
        for endpoint in ('/api/files', '/api/download', '/api/download-zip', '/api/folders',
                         '/api/rename', '/api/delete'):
            self.assertIn(endpoint, self.browser)
        self.assertIn('share_root', self.browser)
        self.assertIn('Authorization', self.browser)
        self.assertIn('OutFile', self.browser)
        self.assertIn('CheckBoxes=$true', self.browser)

    def test_browse_shortcut_and_share_confinement(self):
        self.assertIn('neon-client.bat', self.bat)
        self.assertIn('-Browse', self.bat)
        self.assertIn('Valid-RelativePath', self.browser)
        self.assertIn("$relative -match '(^|/)\\.\\.(/|$)'", self.browser)
        self.assertIn('outside the configured Pi share', self.browser)


if __name__ == '__main__':
    unittest.main()
