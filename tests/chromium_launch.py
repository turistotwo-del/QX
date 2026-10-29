"""Use locally installed Chrome/Chromium or Playwright-managed Chromium in CI."""
import shutil


def launch_chromium(playwright):
    binary=(shutil.which('chromium') or shutil.which('chrome') or
            shutil.which('google-chrome') or shutil.which('google-chrome-stable'))
    opts={'headless':True,'args':['--no-sandbox']}
    if binary:
        opts['executable_path']=binary
    return playwright.chromium.launch(**opts)
