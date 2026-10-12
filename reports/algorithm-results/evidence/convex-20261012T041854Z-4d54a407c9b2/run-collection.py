# Supplemental low-frequency host observation; the reviewed collector is unchanged.
from pathlib import Path
import ctypes,json,time,threading,subprocess,datetime,sys
from ctypes import wintypes
b=Path(__file__).resolve().parent
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
gettimes=kernel.GetSystemTimes
gettimes.argtypes=[ctypes.POINTER(wintypes.FILETIME)]*3;gettimes.restype=wintypes.BOOL
stop=threading.Event();samples=[]
def sample():
    before=None
    while not stop.is_set():
        vals=[wintypes.FILETIME() for _ in range(3)]
        ok=gettimes(*(ctypes.byref(x) for x in vals))
        row={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'monotonic_ns':time.perf_counter_ns(),'available':bool(ok)}
        if ok:
            now=[(x.dwHighDateTime<<32)|x.dwLowDateTime for x in vals]
            row.update(dict(zip(('idle_100ns','kernel_including_idle_100ns','user_100ns'),now)))
            if before:
                idle,kern,user=[x-y for x,y in zip(now,before)];total=kern+user
                row['all_processors_busy_percent']=100*(total-idle)/total if total else None
            before=now
        else:row['error']=ctypes.get_last_error()
        samples.append(row);stop.wait(.25)
command=[sys.executable,'scripts/reports/collect_convex.py','--exe',str(b/'Release/csl_convex_report.exe'),'--build-info',str(b/'report-build-info.json'),'--build-log',str(b/'release-build.log'),'--source-commit','cc3d91b579d1bfbb07fb6159b6709a08cd15fa10','--repetitions','7','--warmups','1','--profile-rounds','1000','--concurrent-work-file',str(b/'concurrent-work.txt'),'--out',str(b/'collection-001')]
thread=threading.Thread(target=sample);thread.start();started=datetime.datetime.now(datetime.timezone.utc).isoformat()
try:
    with (b/'collector-stdout.txt').open('xb') as out,(b/'collector-stderr.txt').open('xb') as err:
        result=subprocess.run(command,stdout=out,stderr=err,timeout=1500)
    code=result.returncode
finally:
    stop.set();thread.join()
    payload={'source':'Windows GetSystemTimes','scope':'250ms wall samples during the entire unchanged collector process, including final provenance build and machine snapshots; not native/per-trial CPU','kernel_includes_idle':True,'sampled_process':'lightweight collector-launcher thread; overhead not subtracted','started_utc':started,'ended_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'samples':samples}
    (b/'host-load-during.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
result={'command':command,'started_utc':started,'ended_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'return_code':code,'samples':len(samples)}
(b/'collector-run.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2));raise SystemExit(code)
