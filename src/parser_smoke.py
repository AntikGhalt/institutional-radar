import concurrent.futures, datetime as dt
from src import radar
from src.calendars import adapter
def main():
    start=radar.run_date()+dt.timedelta(days=1)
    end=start+dt.timedelta(days=29)
    sources=[s for s in radar.SOURCES if s["name"] in {"ISTAT","Eurostat","INPS","MLPS","Banca d’Italia"}]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        result=list(ex.map(lambda s:adapter(s,start,end,sample_dir=radar.ROOT/"output"/"parser-fixtures"),sources))
    records=[{"institution":s["name"],"events":rows,"parser":info} for s,(rows,info) in zip(sources,result)]
    radar.write(radar.ROOT/"output"/"parser-smoke.json",records)
    for record in records:
        print(record["institution"],record["parser"]["status"],len(record["events"]),record["parser"]["attempts"])
    if any(not r["events"] for r in records): print("WARNING: at least one adapter returned no in-horizon candidates; audit diagnostics before production.")
if __name__=="__main__": main()
