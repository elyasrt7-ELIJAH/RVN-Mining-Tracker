@echo off
cd /d %~dp0

echo =====================
echo RAVENMINER RVN START
echo =====================

REM This launches the Python tracker script, which starts t-rex.exe
REM and logs mining time to Mining_History.csv.
REM The pool, wallet address, and algorithm are configured inside
REM RVN_Mining_Tracker.py (the wallet address there is a TEST address -
REM replace it with your own RVN wallet before mining for real).

python RVN_Mining_Tracker.py

pause
