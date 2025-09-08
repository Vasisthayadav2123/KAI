import os
import platform

def sleep_laptop():
    system = platform.system()

    if system == "Windows":
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")

if __name__ == "__main__":
    sleep_laptop()
    