from dataclasses import *

@dataclass
class Color:
    dont: bool = False
    def set_enabled(self, use_color: bool):
        self.dont = not use_color
    reset: str = '\033[0m'
    def none       (self, s: str) -> str: return s
    def black      (self, s: str) -> str: return s if self.dont else ('\033[30m' + s + self.reset)
    def red        (self, s: str) -> str: return s if self.dont else ('\033[31m' + s + self.reset)
    def green      (self, s: str) -> str: return s if self.dont else ('\033[32m' + s + self.reset)
    def orange     (self, s: str) -> str: return s if self.dont else ('\033[33m' + s + self.reset)
    def blue       (self, s: str) -> str: return s if self.dont else ('\033[34m' + s + self.reset)
    def purple     (self, s: str) -> str: return s if self.dont else ('\033[35m' + s + self.reset)
    def cyan       (self, s: str) -> str: return s if self.dont else ('\033[36m' + s + self.reset)
    def lightgrey  (self, s: str) -> str: return s if self.dont else ('\033[37m' + s + self.reset)
    def darkgrey   (self, s: str) -> str: return s if self.dont else ('\033[90m' + s + self.reset)
    def lightred   (self, s: str) -> str: return s if self.dont else ('\033[91m' + s + self.reset)
    def lightgreen (self, s: str) -> str: return s if self.dont else ('\033[92m' + s + self.reset)
    def yellow     (self, s: str) -> str: return s if self.dont else ('\033[93m' + s + self.reset)
    def lightblue  (self, s: str) -> str: return s if self.dont else ('\033[94m' + s + self.reset)
    def pink       (self, s: str) -> str: return s if self.dont else ('\033[95m' + s + self.reset)
    def lightcyan  (self, s: str) -> str: return s if self.dont else ('\033[96m' + s + self.reset)

color = Color()
