# Quick start

## Before you begin

Install 64-bit CPython 3.13.x for Windows 11, including the Python Launcher. Confirm it from PowerShell:

```powershell
py -3.13 --version
```

No other Python version is supported by personal V1.

## First launch

1. Extract or clone the complete application folder.
2. Double-click `Launch ML Learning Lab.cmd`.
3. Leave the launcher window open while using the app.
4. Allow the first setup to download the exact packages in `requirements.lock`.
5. The browser opens at `http://127.0.0.1:8501`.

Later launches reuse the environment and work offline while the dependency lock is unchanged.

## Review the vertical slice

1. Open **Start here** to see the spreadsheet-to-pandas bridge.
2. Open **Learn: F1**.
3. Complete Understand, Explore, Code, and Check in any order.
4. Open **Progress & settings** and download the versioned progress JSON.
5. Open **Evidence export** and download the validated ZIP.

## Stop and restart

Press `Ctrl+C` in the launcher window to stop Streamlit. Double-click the launcher again to resume. Lesson evidence remains under `%LOCALAPPDATA%\MLLearningLab\state`.
