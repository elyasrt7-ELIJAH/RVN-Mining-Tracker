# RVN_Mining_Tracker v1.6.0 (local estimate only - pool lookup removed, OK/FAIL/temperature colorization)
import os,sys,csv,time,re,threading,subprocess,traceback,signal,atexit
from datetime import datetime,timedelta

TREX="t-rex.exe";POOL="stratum+tcp://stratum.ravenminer.com:3838"
# NOTE: This is a TEST wallet address for demonstration purposes only.
# Replace it with your own RVN wallet address before mining for real.
WALLET="RMiEA9wNM5Bc3vrmqjxAKPxFa1B29mVYmW.test";ALGO="kawpow"
CSV="Mining_History.csv";TMP="Session.tmp";LOG="Error_Log.txt"
miner=None;start_time=None;running=False;cleanup_done=False
hash_sum=0.0;hash_count=0   # running total for current session's average hashrate

COIN_RATE=0.5         # RVN awarded per hour of mining (used as a fallback estimate only, since the pool no longer responds)
HASH_RE=re.compile(r'(\d+\.\d+\s*MH/s)')
HASHVAL_RE=re.compile(r'(\d+\.\d+)\s*MH/s')
UPTIME_RE=re.compile(r'(Uptime:\s*)(.*?)(\s*\|)')
OK_RE=re.compile(r'\[ OK \]')
FAIL_RE=re.compile(r'\[FAIL\]')
TEMP_RE=re.compile(r'T:(\d+)C')

def err():
    with open(LOG,"a",encoding="utf-8") as f:
        f.write(f"\n[{datetime.now()}]\n{traceback.format_exc()}\n")

def migrate_csv():
    # adds a "Coins" column to an older CSV file that doesn't have it yet, without losing data
    if not os.path.exists(CSV):return
    try:
        with open(CSV,encoding="utf-8") as f:
            rows=list(csv.reader(f))
        if not rows or "Coins" in rows[0]:return
        rows[0].append("Coins")
        for row in rows[1:]:
            row.append("0")
        with open(CSV,"w",newline="",encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
    except: err()

def hist(s,e):
    secs=max(0,round((e-s).total_seconds()))
    coins=round(secs/3600*COIN_RATE,4)
    migrate_csv()
    new=not os.path.exists(CSV)
    with open(CSV,"a",newline="",encoding="utf-8") as f:
        w=csv.writer(f)
        if new:w.writerow(["Date","Coin","Start","End","Duration","Coins"])
        w.writerow([s.strftime("%Y-%m-%d"),"RVN",s.strftime("%H:%M:%S"),e.strftime("%H:%M:%S"),str(timedelta(seconds=secs)),coins])

def recover():
    if not os.path.exists(TMP):return
    try:
        d={}
        with open(TMP,encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    k,v=line.strip().split("=",1);d[k]=v
        s=datetime.strptime(d["Start"],"%Y-%m-%d %H:%M:%S")
        e=datetime.strptime(d["LastSave"],"%Y-%m-%d %H:%M:%S")
        hist(s,e)
    except: err()
    finally:
        try:
            if os.path.exists(TMP): os.remove(TMP)
        except: pass

def cleanup():
    global cleanup_done,running
    if cleanup_done:return
    cleanup_done=True
    if running and start_time:
        try: hist(start_time,datetime.now())
        except: err()
    running=False
    try:
        if os.path.exists(TMP): os.remove(TMP)
    except: pass

def parse_dur(s):
    try:
        if "day" in s:
            d,rest=s.split(",")
            days=int(d.strip().split(" ")[0])
            h,m,sec=[int(x) for x in rest.strip().split(":")]
            return timedelta(days=days,hours=h,minutes=m,seconds=sec)
        h,m,sec=[int(x) for x in s.strip().split(":")]
        return timedelta(hours=h,minutes=m,seconds=sec)
    except:
        return timedelta(0)

def fmt_hm(td):
    # hours:minutes only, no seconds
    total_min=max(0,round(td.total_seconds()/60))
    h,m=divmod(total_min,60)
    return f"{h}:{m:02d}"

def fmt_hours(td):
    # total hours only (e.g. "100.0h", "200.0h")
    hours=max(0.0,td.total_seconds())/3600
    return f"{hours:.1f}h"

# enable ANSI colors on Windows console (cmd.exe)
if os.name=="nt":
    os.system("")

GREEN="\033[92m";YELLOW="\033[93m";RED="\033[91m";BLUE="\033[94m";CYAN="\033[96m";BOLD="\033[1m";RESET="\033[0m"
DAY_H=24;WEEK_D=7;MONTH_D=30;YEAR_D=365

def show_stats():
    if not os.path.exists(CSV):return
    try:
        now=datetime.now()
        today=now.date()
        # Fixed windows (not calendar-based): week=7d, month=30d, year=365d
        week_start=today-timedelta(days=WEEK_D-1)
        month_start=today-timedelta(days=MONTH_D-1)
        year_start=today-timedelta(days=YEAR_D-1)
        grand_tot=timedelta();day_tot=timedelta();week_tot=timedelta();month_tot=timedelta();year_tot=timedelta()
        first_date=None;last_date=None;coins_tot=0.0
        with open(CSV,encoding="utf-8") as f:
            r=csv.DictReader(f)
            for row in r:
                try:
                    d=datetime.strptime(row["Date"],"%Y-%m-%d").date()
                except:
                    continue
                dur=parse_dur(row["Duration"])
                grand_tot+=dur
                try: coins_tot+=float(row.get("Coins",0) or 0)
                except: pass
                if first_date is None or d<first_date: first_date=d
                if last_date is None or d>last_date: last_date=d
                if d==today: day_tot+=dur
                if week_start<=d<=today: week_tot+=dur
                if month_start<=d<=today: month_tot+=dur
                if year_start<=d<=today: year_tot+=dur
        month_avg=month_tot/MONTH_D
        year_avg=year_tot/YEAR_D
        total_coins=coins_tot
        print(f"\n{BOLD}{CYAN}Last run:  {now.strftime('%Y-%m-%d %H:%M:%S')}{RESET}")
        print("=== Mining Stats ===")
        print(f"First mine:  {first_date.strftime('%Y-%m-%d') if first_date else '-'}")
        print(f"Last mine:   {last_date.strftime('%Y-%m-%d') if last_date else '-'}")
        print(f"Grand total: {fmt_hours(grand_tot)}")
        print(f"{GREEN}Today:       {fmt_hm(day_tot)}{RESET}")
        print(f"{YELLOW}7-day total: {fmt_hm(week_tot)}{RESET}")
        print(f"{RED}Month avg:   {fmt_hm(month_avg)}/day ({MONTH_D}d){RESET}")
        print(f"Year avg:    {fmt_hm(year_avg)}/day ({YEAR_D}d)")
        print(f"{YELLOW}Est. coins:  {total_coins:.2f} RVN ({COIN_RATE}/h){RESET}")
        if hash_count>0:
            print(f"{BLUE}Avg hashrate (session): {hash_sum/hash_count:.2f} MH/s{RESET}")
        print("=====================")
    except:
        err()

def sig(*_):
    global miner
    try:
        if miner and miner.poll() is None: miner.terminate()
    except: pass
    cleanup()
    show_stats()
    raise SystemExit

atexit.register(cleanup)
signal.signal(signal.SIGINT,sig)
if hasattr(signal,"SIGTERM"): signal.signal(signal.SIGTERM,sig)

def autosave():
    while running:
        with open(TMP,"w",encoding="utf-8") as f:
            f.write(f"Running=True\nStart={start_time:%Y-%m-%d %H:%M:%S}\nLastSave={datetime.now():%Y-%m-%d %H:%M:%S}\n")
        time.sleep(30)

def live_clock():
    # Lightweight live clock + running avg hashrate shown in the console title bar.
    # Uses the ANSI OSC-0 title escape (works in cmd.exe and Windows Terminal),
    # not the older SetConsoleTitleW call which some terminals ignore.
    while True:
        try:
            hr=f"{hash_sum/hash_count:.1f}MH/s" if hash_count>0 else "n/a"
            title=f"RVN Miner - {datetime.now():%H:%M:%S} - Avg:{hr}"
            sys.stdout.write(f"\x1b]0;{title}\x07")
            sys.stdout.flush()
        except: pass
        time.sleep(1)

threading.Thread(target=live_clock,daemon=True).start()

try:
    recover()
    show_stats()  # print stats at every startup
    miner=subprocess.Popen([TREX,"-a",ALGO,"-o",POOL,"-u",WALLET],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
    for line in miner.stdout:
        out=line
        if "MH/s" in line:
            out=HASH_RE.sub(lambda m:f"{BLUE}{m.group(1)}{RESET}",out)
            hv=HASHVAL_RE.search(line)
            if hv:
                hash_sum+=float(hv.group(1));hash_count+=1
                avg=hash_sum/hash_count
                out=out.rstrip("\n")+f" {CYAN}[Avg:{avg:.2f}MH/s]{RESET}\n"
        if "Uptime:" in line:
            out=UPTIME_RE.sub(lambda m:f"{m.group(1)}{RED}{m.group(2)}{RESET}{m.group(3)}",out)
        if "[ OK ]" in line:
            out=OK_RE.sub(f"{GREEN}[ OK ]{RESET}",out)
        if "[FAIL]" in line:
            out=FAIL_RE.sub(f"{BOLD}{RED}[FAIL]{RESET}",out)
        if "T:" in line:
            out=TEMP_RE.sub(lambda m:f"T:{GREEN}{m.group(1)}{RESET}C",out)
        print(out,end="")
        if not running and "Mining at" in line:
            start_time=datetime.now();running=True
            threading.Thread(target=autosave,daemon=True).start()
    miner.wait()
finally:
    cleanup()
    show_stats()
