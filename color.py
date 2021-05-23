
reset      = '\033[0m'
def none       (s: str) -> str: return              s
def black      (s: str) -> str: return '\033[30m' + s + reset
def red        (s: str) -> str: return '\033[31m' + s + reset
def green      (s: str) -> str: return '\033[32m' + s + reset
def orange     (s: str) -> str: return '\033[33m' + s + reset
def blue       (s: str) -> str: return '\033[34m' + s + reset
def purple     (s: str) -> str: return '\033[35m' + s + reset
def cyan       (s: str) -> str: return '\033[36m' + s + reset
def lightgrey  (s: str) -> str: return '\033[37m' + s + reset
def darkgrey   (s: str) -> str: return '\033[90m' + s + reset
def lightred   (s: str) -> str: return '\033[91m' + s + reset
def lightgreen (s: str) -> str: return '\033[92m' + s + reset
def yellow     (s: str) -> str: return '\033[93m' + s + reset
def lightblue  (s: str) -> str: return '\033[94m' + s + reset
def pink       (s: str) -> str: return '\033[95m' + s + reset
def lightcyan  (s: str) -> str: return '\033[96m' + s + reset
