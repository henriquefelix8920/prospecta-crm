import asyncio, os, sqlite3, threading, time, uuid, csv, io
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
DB=os.getenv("DATABASE_PATH","prospecta.db"); app=FastAPI(title="Prospecta CRM"); JOBS={}; LOCK=threading.Lock()
def db():
 c=sqlite3.connect(DB,check_same_thread=False); c.row_factory=sqlite3.Row
 c.execute("""CREATE TABLE IF NOT EXISTS leads(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,category TEXT DEFAULT '',phone TEXT DEFAULT '',website TEXT DEFAULT '',address TEXT DEFAULT '',maps_url TEXT DEFAULT '',status TEXT DEFAULT 'Novo',notes TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(name,address))"""); c.commit(); return c
class Search(BaseModel):
 city:str=Field(min_length=2,max_length=100); category:str=Field(min_length=2,max_length=100); limit:int=Field(default=10,ge=1,le=20)
class LeadUpdate(BaseModel):
 status:Optional[str]=None; notes:Optional[str]=None; phone:Optional[str]=None; website:Optional[str]=None
@app.get("/health")
def health(): return {"ok":True}
@app.get("/",response_class=HTMLResponse)
def home(): return Path("index.html").read_text(encoding="utf-8")
@app.get("/api/leads")
def leads(q:str="",status:str=""):
 c=db(); sql="SELECT * FROM leads WHERE (name LIKE ? OR phone LIKE ? OR category LIKE ? OR address LIKE ?)"; p=[f"%{q}%"]*4
 if status: sql+=" AND status=?"; p.append(status)
 rows=[dict(x) for x in c.execute(sql+" ORDER BY id DESC",p).fetchall()]; c.close(); return rows
@app.patch("/api/leads/{lead_id}")
def update_lead(lead_id:int,data:LeadUpdate):
 vals={k:v for k,v in data.model_dump(exclude_none=True).items() if k in {"status","notes","phone","website"}}
 if vals:
  c=db(); c.execute("UPDATE leads SET "+", ".join(k+"=?" for k in vals)+" WHERE id=?",[*vals.values(),lead_id]); c.commit(); c.close()
 return {"ok":True}
@app.post("/api/search")
def start_search(data:Search):
 jid=str(uuid.uuid4())[:8]
 with LOCK: JOBS[jid]={"id":jid,"state":"queued","message":"Na fila","found":0}
 threading.Thread(target=run_search,args=(jid,data),daemon=True).start(); return JOBS[jid]
@app.get("/api/jobs/{jid}")
def job(jid:str):
 if jid not in JOBS: raise HTTPException(404,"Busca não encontrada")
 return JOBS[jid]
def setjob(jid,**kw):
 with LOCK: JOBS[jid].update(kw)
def run_search(jid,data):
 try: asyncio.run(scrape(jid,data))
 except Exception as e: setjob(jid,state="error",message="Falha: "+str(e)[:200])
async def scrape(jid,data):
 from playwright.async_api import async_playwright
 from urllib.parse import quote
 setjob(jid,state="running",message="Abrindo Google Maps…")
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,args=["--no-sandbox","--disable-dev-shm-usage"])
  page=await browser.new_page(locale="pt-BR")
  await page.goto("https://www.google.com/maps/search/"+quote(data.category+" em "+data.city),wait_until="domcontentloaded",timeout=60000)
  try: await page.locator('div[role="feed"]').wait_for(timeout=25000)
  except:
   await browser.close(); raise RuntimeError("Google Maps não apresentou resultados. Pode haver CAPTCHA ou bloqueio temporário.")
  feed=page.locator('div[role="feed"]'); links=set()
  for _ in range(8):
   for a in await page.locator('a[href*="/maps/place/"]').all():
    href=await a.get_attribute("href")
    if href: links.add(href)
    if len(links)>=data.limit: break
   if len(links)>=data.limit: break
   await feed.evaluate("el => el.scrollBy(0, Math.max(el.scrollHeight, 700))"); await page.wait_for_timeout(1100)
  urls=list(links)[:data.limit]; found=0
  for i,url in enumerate(urls):
   setjob(jid,message=f"Analisando empresa {i+1} de {len(urls)}…",found=found)
   try:
    await page.goto(url,wait_until="domcontentloaded",timeout=30000); await page.wait_for_timeout(900)
    h=page.locator("h1").first; name=(await h.inner_text()).strip() if await h.count() else ""
    if not name: continue
    address=phone=website=""
    for sel,kind in [('button[data-item-id="address"]',"address"),('button[data-item-id^="phone:"]',"phone"),('a[data-item-id="authority"]',"website")]:
     el=page.locator(sel).first
     if await el.count():
      val=(await el.get_attribute("aria-label")) or (await el.inner_text())
      if kind=="address": address=val.replace("Endereço:","").strip()
      elif kind=="phone": phone=val.replace("Telefone:","").strip()
      else: website=await el.get_attribute("href") or ""
    c=db(); c.execute("INSERT OR IGNORE INTO leads(name,category,phone,website,address,maps_url) VALUES(?,?,?,?,?,?)",(name,data.category,phone,website,address,url))
    if c.execute("SELECT changes()").fetchone()[0]: found+=1
    c.commit(); c.close()
   except Exception: continue
  await browser.close()
 setjob(jid,state="done",message="Captura concluída",found=found)
@app.get("/api/export.csv")
def export_csv():
 c=db(); rows=c.execute("SELECT name,category,phone,website,address,status,notes,maps_url FROM leads ORDER BY id DESC").fetchall(); c.close()
 out=io.StringIO(); w=csv.writer(out); w.writerow(["Empresa","Categoria","Telefone","Site","Endereço","Etapa","Observações","Google Maps"]); w.writerows([tuple(r) for r in rows])
 return StreamingResponse(iter(["\ufeff"+out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=prospecta-leads.csv"})
