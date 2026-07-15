"""Pattern 2 - launch the patched Huligan binary under a driver that spawns Chrome
itself (Selenium, undetected-chromedriver, ...).

Three ingredients, no adapter class:
  1. binary_location = huligan.ensure_binary()   # the patched build (never a system chrome)
  2. huligan.get_default_stealth_args()          # --no-sandbox + the JA4/TLS pins
  3. HULIGAN_CONFIG_PATH -> a generated .conf     # the fingerprint itself

The flags alone do NOT carry a fingerprint; ingredient 3 is load-bearing.

    pip install huligan selenium
    python selenium_binary_and_args.py
"""
import os
import tempfile

from huligan import FingerprintGenerator, ensure_binary, get_default_stealth_args


def main():
    # 1) The patched binary (downloads + caches on first use; never a system chrome).
    binary = ensure_binary()

    # 2) A fingerprint .conf, wired via the ABSOLUTE HULIGAN_CONFIG_PATH the binary
    #    reads on startup (must be absolute - Chrome changes CWD).
    profile = FingerprintGenerator().generate()
    conf_path = os.path.abspath("identity.conf")
    with open(conf_path, "w", encoding="utf-8") as f:
        f.write(profile.to_conf())
    os.environ["HULIGAN_CONFIG_PATH"] = conf_path

    # 3) Hand the binary + stealth flags to the driver. You own --user-data-dir.
    from selenium import webdriver

    opts = webdriver.ChromeOptions()
    opts.binary_location = str(binary)
    for arg in get_default_stealth_args():
        opts.add_argument(arg)
    opts.add_argument(f"--user-data-dir={tempfile.mkdtemp(prefix='huligan_sel_')}")

    driver = webdriver.Chrome(options=opts)
    try:
        driver.get("https://browserleaks.com/javascript")
        print("browserVersion:", driver.capabilities.get("browserVersion"))
        print("navigator.webdriver:", driver.execute_script("return navigator.webdriver"))
    finally:
        driver.quit()

    # undetected-chromedriver is a drop-in: uc.ChromeOptions() has the identical
    # binary_location + add_argument surface, so the same three ingredients apply.
    #
    # NOTE: patch 05_cdp_stealth isolates the CDP main world. If driver.execute_script
    # misbehaves under heavy JS injection, prefer Pattern 1 (CDP connect).


if __name__ == "__main__":
    main()
