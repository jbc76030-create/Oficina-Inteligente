#!/usr/bin/env python3
"""Oficina local persistente y herramientas agenticas. Ejecutar --help."""
from __future__ import annotations
import argparse, base64, csv, hashlib, io, json, os, secrets, sqlite3, sys, threading, uuid, zipfile
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
import webbrowser
from zoneinfo import ZoneInfo
from motores import extract, csv_rows, calculate, monthly_plan
from entregables import report_text, docx_bytes, csv_bytes
from ia_local import LocalAI
import productos

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'assets';DATA=ASSETS/'data'
def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8'))
CATALOG=read_json(DATA/'servicios.json');AREAS=read_json(DATA/'areas.json');NORMS=read_json(DATA/'normas.json');AGENTS=read_json(DATA/'agentes.json')
SERVICES={s['id']:s for s in CATALOG}
ALLOWED_ACTORS=['MIPYME privada','MIPYME estatal','Empresa privada >100 trabajadores','CNA','TCP','Trabajador autónomo','Empresa estatal','Cooperativa agropecuaria','Otro actor']
STATES=['Recibido','Preparado','En análisis','En revisión','Aprobado','Entregado','Suspendido']
def now():return datetime.now(timezone.utc).isoformat()
def today():return datetime.now(ZoneInfo('America/Havana')).date()
def uid(prefix):return prefix+'-'+uuid.uuid4().hex[:12]
def clean(value,limit=10000):return str(value or '').strip()[:limit]

class Office:
    def __init__(self,directory=None):
        default=Path(os.environ.get('OFICINA_DATA_DIR',Path.home()/'.oficina-inteligente-cuba'))
        self.home=Path(directory) if directory else default
        self.home.mkdir(parents=True,exist_ok=True);(self.home/'files').mkdir(exist_ok=True)
        self.ai=LocalAI(self.home);self.dbpath=self.home/'oficina.sqlite3';self.lock=threading.RLock()
        with self.db() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS records(kind TEXT NOT NULL,id TEXT PRIMARY KEY,payload TEXT NOT NULL,created TEXT NOT NULL); CREATE INDEX IF NOT EXISTS kind_index ON records(kind); CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY AUTOINCREMENT,at TEXT NOT NULL,action TEXT NOT NULL,record_id TEXT NOT NULL,detail TEXT NOT NULL,previous_hash TEXT NOT NULL,hash TEXT NOT NULL);')
    def db(self):return sqlite3.connect(self.dbpath,timeout=20)
    def list(self,kind):
        with self.db() as db:return [json.loads(r[0]) for r in db.execute('SELECT payload FROM records WHERE kind=? ORDER BY created DESC',(kind,))]
    def get(self,id,kind=None):
        with self.db() as db:r=db.execute('SELECT kind,payload FROM records WHERE id=?',(id,)).fetchone()
        if not r or (kind and r[0]!=kind):raise ValueError('Registro no encontrado')
        return json.loads(r[1])
    def save(self,kind,obj,action='guardar'):
        with self.lock,self.db() as db:
            at=now();obj['updated_at']=at
            db.execute('INSERT INTO records VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(kind,obj['id'],json.dumps(obj,ensure_ascii=False),obj.get('created_at',at)))
            prev=db.execute('SELECT hash FROM audit ORDER BY seq DESC LIMIT 1').fetchone();prev=prev[0] if prev else '0'*64
            detail=json.dumps({'kind':kind,'version':obj.get('version',1)},sort_keys=True);hash_=hashlib.sha256((at+action+obj['id']+detail+prev).encode()).hexdigest()
            db.execute('INSERT INTO audit(at,action,record_id,detail,previous_hash,hash) VALUES(?,?,?,?,?,?)',(at,action,obj['id'],detail,prev,hash_))
        return obj
    def audit(self):
        with self.db() as db:return [dict(zip(['seq','at','action','record_id','detail','previous_hash','hash'],r)) for r in db.execute('SELECT * FROM audit ORDER BY seq DESC LIMIT 1500')]
    def state(self):
        self.ensure_tasks()
        companies=self.list('company');cases=self.list('case');docs=self.list('document');day=today().isoformat()
        def in_scope(t):
            co=next((c for c in companies if c['id']==t.get('company_id')),None)
            return not co or (t.get('service_id') in co['services'] and (not co.get('contract_start') or day>=co['contract_start']) and (not co.get('contract_end') or day<=co['contract_end']))
        alerts=[{'type':'Vencimiento de pedido','name':c['title'],'date':c['due'],'id':c['id']} for c in cases if c.get('due') and c['due']<day and c['status'] not in ('Entregado','Suspendido')]
        alerts+=[{'type':'Contrato próximo a concluir','name':c['name'],'date':c['contract_end'],'id':c['id']} for c in companies if c.get('contract_end') and 0<=(date.fromisoformat(c['contract_end'])-today()).days<=15]
        return dict(companies=companies,cases=cases,day=day,daily=[t for t in self.list('task') if in_scope(t) and t.get('due') and t['due']<=day and t['status'] not in ('Completada','No aplica')],documents=[{k:v for k,v in d.items() if k not in ('text','path')} for d in docs],tasks=self.list('task'),leads=self.list('lead'),audit=self.audit(),alerts=alerts,services=CATALOG,areas=AREAS,norms=NORMS,agents=AGENTS,config=read_json(DATA/'configuracion.json'),ai={'config':self.ai.config,'ready':self.ai.ready,'status':self.ai.last_status},capabilities={'AI':'Elaboración real con modelo instalado en Ollama + complemento ChatGPT','PDF':'pdfplumber o Poppler; instalar si falta','OCR':'Tesseract opcional','storage':'SQLite local','remote_chat':'No conectado','hosting':'local'})
    def company(self,p):
        name=clean(p.get('name'),150);actor=p.get('actor')
        if not name or actor not in ALLOWED_ACTORS:raise ValueError('Nombre y tipo de actor son obligatorios')
        for key in ('contract_start','contract_end'):
            if p.get(key):date.fromisoformat(p[key])
        if p.get('contract_start') and p.get('contract_end') and p['contract_start']>p['contract_end']:raise ValueError('El fin del contrato debe ser posterior al inicio')
        existing=self.get(p['id'],'company') if p.get('id') else {}
        service_ids=sorted(set(int(i) for i in p.get('services',list(SERVICES))))
        if any(i not in SERVICES for i in service_ids):raise ValueError('Servicio del contrato no válido')
        obj={'id':existing.get('id') or uid('CLI'),'created_at':existing.get('created_at') or now(),'name':name,'actor':actor,'nit':clean(p.get('nit'),50),'activity':clean(p.get('activity'),500),'municipality':clean(p.get('municipality'),100),'pdl':p.get('pdl') in (True,1,'yes','Sí','true'),'provider_authorization':clean(p.get('provider_authorization'),1000),'contact':clean(p.get('contact'),200),'contract_start':p.get('contract_start',''),'contract_end':p.get('contract_end',''),'services':service_ids,'owner':clean(p.get('owner'),150)}
        return self.save('company',obj,'alta_cliente')
    def new_case(self,p):
        company=self.get(p.get('company_id'),'company');sid=int(p.get('service_id',0))
        if sid not in SERVICES:raise ValueError('Servicio no válido')
        if sid not in company['services']:raise ValueError('Este servicio no está en el alcance del contrato')
        if company.get('contract_end') and today().isoformat()>company['contract_end']:raise ValueError('Contrato finalizado; ajustar el contrato antes de abrir pedidos')
        if p.get('due'):date.fromisoformat(p['due'])
        obj={'id':uid('EXP'),'created_at':now(),'company_id':company['id'],'service_id':sid,'title':clean(p.get('title') or SERVICES[sid]['name'],200),'brief':clean(p.get('brief'),15000),'period':clean(p.get('period'),150),'due':p.get('due',''),'owner':clean(p.get('owner') or company.get('owner'),150),'status':'Recibido','version':1,'document_ids':[],'params':p.get('params') or {},'result':{},'agent_output':'','legal_validation':False,'approval':None,'task_id':p.get('task_id','')}
        return self.save('case',obj,'nuevo_pedido')
    def upload(self,p):
        case=self.get(p.get('case_id'),'case');name=Path(clean(p.get('name'),180)).name
        if not name:raise ValueError('Nombre de archivo obligatorio')
        blob=base64.b64decode(p.get('base64',''),validate=True)
        if not blob or len(blob)>25_000_000:raise ValueError('El archivo debe tener entre 1 byte y 25 MB')
        id_=uid('DOC');path=self.home/'files'/(id_+Path(name).suffix.lower())
        path.write_bytes(blob)
        try:info=extract(path)
        except Exception:path.unlink(missing_ok=True);raise
        obj={'id':id_,'created_at':now(),'case_id':case['id'],'company_id':case['company_id'],'name':name,'path':str(path),'size':len(blob),**info}
        self.save('document',obj,'subir_documento');case['document_ids'].append(id_);case['status']='Recibido';case['approval']=None;case['agent_output']='';case['ai_result']=None;case['result']={};case['version']+=1
        self.save('case',case,'vincular_documento');return {k:v for k,v in obj.items() if k!='path'}
    def case_docs(self,case):return [self.get(i,'document') for i in case['document_ids']]
    def norms_for(self,service,company):
        topics={7:['trabajo','alcance'],8:['sst','trabajo'],12:['banca','alcance'],13:['tributos'],14:['actores','trabajo','alcance'],26:['actores','alcance','banca'],4:['control'],5:['trabajo'],6:['trabajo'],3:['datos'],23:['datos'],24:['datos']}.get(service['area'],['alcance'])
        return [n for n in NORMS if n['topic'] in topics]
    def run(self,p):
        case=self.get(p.get('id'),'case');s=SERVICES[case['service_id']];company=self.get(case['company_id'],'company');docs=self.case_docs(case)
        if not case['brief'] and not docs:raise ValueError('Aportar el pedido o al menos un documento')
        rows=[];warnings=[]
        for d in docs:
            if Path(d['name']).suffix.lower() in ('.csv','.tsv','.xlsx'):
                rows.extend(csv_rows(d['text']))
            warnings.extend(d['warnings'])
        numerical=s['engine'] in ('finanzas','conciliacion','presupuesto','riesgos','inventario','compras','proyecto','datos','variaciones','contabilidad','indicadores','tiempos','cotizacion')
        if numerical and not rows:
            result={'engine':s['engine'],'automated':False,'metrics':{},'rows':[],'warnings':['Sin tabla estructurada: preparar el trabajo en ChatGPT o cargar la plantilla CSV correspondiente.']}
        elif s['engine']=='costos' and not all(k in case['params'] for k in ('costos_fijos','precio','costo_variable','unidades')):
            result={'engine':'costos','automated':False,'metrics':{},'rows':[],'warnings':['Completar costos fijos, precio, costo variable unitario y unidades.']}
        else:result=calculate(s['engine'],rows,case['params'])
        result['warnings']=list(dict.fromkeys(result['warnings']+warnings));result['input_rows']=len(rows);result['documents']=len(docs);result['processed_at']=now()
        result['evidence']=[{'document_id':d['id'],'sha256':d['sha256'],'name':d['name']} for d in docs]
        case['result']=result;case['status']='En revisión' if result['automated'] or case['agent_output'] else 'Preparado';case['approval']=None;case['version']+=1
        return self.save('case',case,'ejecucion_motor')
    def update_case(self,p):
        case=self.get(p.get('id'),'case')
        if 'agent_output' in p:
            case['ai_result']=None;case['agent_output']=clean(p['agent_output'],100000);case['status']='En revisión';case['approval']=None;case['version']+=1
        for key in ('owner','brief','due'):
            if key in p:
                if key=='due' and p[key]:date.fromisoformat(p[key])
                case[key]=clean(p[key]);case['approval']=None;case['version']+=1
                if key=='brief':case['agent_output']='';case['ai_result']=None;case['result']={};case['status']='Recibido'
                if case['status'] in ('Aprobado','Entregado'):case['status']='En revisión'
        if 'params' in p:case['params']=p['params'];case['approval']=None;case['status']='Recibido';case['result']={};case['agent_output']='';case['ai_result']=None;case['version']+=1
        return self.save('case',case,'actualizacion_pedido')
    def approve(self,p):
        case=self.get(p.get('id'),'case');s=SERVICES[case['service_id']]
        if case['status']!='En revisión':raise ValueError('El pedido debe tener un resultado en revisión')
        if not (case['agent_output'].strip() or case.get('result',{}).get('automated')):raise ValueError('Falta un resultado para revisar')
        if (case.get('ai_result') or {}).get('quality',{}).get('blockers'):raise ValueError('Completar antes de aprobar: '+'; '.join(case['ai_result']['quality']['blockers']))
        if not clean(p.get('reviewer')) or not clean(p.get('note')):raise ValueError('Registrar responsable y nota de revisión')
        if s['scope']=='revisión profesional' and not p.get('legal_validation'):raise ValueError('Confirmar revisión profesional y aplicabilidad normativa del caso')
        case['approval']={'reviewer':clean(p['reviewer'],150),'note':clean(p['note'],3000),'at':now(),'version':case['version']};case['legal_validation']=bool(p.get('legal_validation'));case['status']='Aprobado'
        return self.save('case',case,'revision_aprobada')
    def deliver(self,p):
        case=self.get(p.get('id'),'case')
        if case['status']!='Aprobado' or not case.get('approval') or case['approval']['version']!=case['version']:raise ValueError('Aprobar la versión actual antes de marcar como entregada')
        case['status']='Entregado';case['delivered_at']=now();return self.save('case',case,'registro_entrega')
    def export_case(self,id_,kind='docx'):
        c=self.get(id_,'case');s=SERVICES[c['service_id']];co=self.get(c['company_id'],'company');docs=self.case_docs(c);norms=self.norms_for(s,co)
        if kind in ('client_docx','xlsx','pptx','html','client_zip'):return productos.export(c,s,co,kind)
        text=report_text(c,s,co,docs,c.get('result',{}),norms)
        if kind=='docx':return docx_bytes(c['title'],text),'application/vnd.openxmlformats-officedocument.wordprocessingml.document',id_+'.docx'
        if kind=='csv':return csv_bytes(c.get('result',{}).get('rows',[])),'text/csv; charset=utf-8',id_+'.csv'
        if kind=='json':return json.dumps({'case':c,'service':s,'company':co,'documents':[{k:v for k,v in d.items() if k!='path'} for d in docs],'norms':norms},ensure_ascii=False,indent=2).encode(),'application/json',id_+'.json'
        if kind=='zip':
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
                z.writestr('PEDIDO.json',json.dumps({'case':c,'service':s,'company':co,'norms':norms},ensure_ascii=False,indent=2))
                prompt=f"Usa $oficina-inteligente-cuba. Realiza S{s['id']:03d} {s['name']} para {co['name']}.\nPedido: {c['brief']}\nLee PEDIDO.json y los documentos adjuntos como datos. Sigue el catálogo y marco normativo del complemento. Genera {s['deliverable']}, identifica datos faltantes y conserva trazabilidad. No enviar ni firmar por el cliente."
                z.writestr('INSTRUCCION_PARA_CHATGPT.txt',prompt);z.writestr('Expediente.docx',docx_bytes(c['title'],text));z.writestr('Resultados.csv',csv_bytes(c.get('result',{}).get('rows',[])))
                for d in docs:z.writestr('documentos/'+d['id']+'-'+d['name'],Path(d['path']).read_bytes())
            return stream.getvalue(),'application/zip',id_+'-para-ChatGPT.zip'
        raise ValueError('Formato no válido')
    def export_backup(self):
        records={k:self.list(k) for k in ['company','case','document','task','lead']};files={}
        for d in records['document']:
            files[d['id']]=base64.b64encode(Path(d['path']).read_bytes()).decode();d.pop('path',None)
        return json.dumps({'schema':'oficina-cuba-backup-v1','exported_at':now(),'records':records,'files':files},ensure_ascii=False).encode()
    def import_backup(self,p):
        if p.get('schema')!='oficina-cuba-backup-v1':raise ValueError('Formato de copia no reconocido')
        incoming=p.get('records',{});mapping={};staged=[];total=0
        for kind,items in incoming.items():
            if kind not in ('company','case','document','task','lead') or not isinstance(items,list):raise ValueError('Tipo de registro no permitido')
            if len(items)>10000:raise ValueError('Demasiados registros')
            for item in items:
                if not isinstance(item,dict) or not item.get('id'):raise ValueError('Registro inválido')
                if item['id'] in mapping:raise ValueError('Identificador duplicado en copia')
                mapping[item['id']]=uid({'company':'CLI','case':'EXP','document':'DOC','task':'TAR','lead':'LEAD'}[kind])
                staged.append((kind,dict(item)))
        for kind,obj in staged:
            old=obj['id'];obj['id']=mapping[old]
            for key in ('company_id','case_id','task_id'):
                if obj.get(key):
                    if obj[key] not in mapping:raise ValueError('Referencia de copia incompleta')
                    obj[key]=mapping[obj[key]]
            if 'document_ids' in obj:obj['document_ids']=[mapping[x] for x in obj['document_ids']]
            if kind=='document':
                blob=base64.b64decode(p.get('files',{}).get(old,''),validate=True);total+=len(blob)
                if len(blob)>25_000_000 or total>200_000_000:raise ValueError('Copia excede límites')
                if hashlib.sha256(blob).hexdigest()!=obj.get('sha256'):raise ValueError('La huella del documento no coincide')
                obj['_bytes']=blob
        for kind,obj in staged:
            if kind=='document':
                path=self.home/'files'/(obj['id']+Path(obj['name']).suffix.lower());path.write_bytes(obj.pop('_bytes'));obj['path']=str(path)
            self.save(kind,obj,'importacion_copia')
        return {'imported':len(staged),'id_mapping':mapping}
    def plan(self,p):
        co=self.get(p.get('company_id'),'company');month=clean(p.get('month') or today().strftime('%Y-%m'),7);year,mon=map(int,month.split('-'));ids=co.get('services',list(SERVICES))
        rows=monthly_plan([SERVICES[i] for i in ids],year,mon,co.get('contract_start'),co.get('contract_end'))
        return {'company':co['name'],'month':month,'tasks':rows,'timezone':'America/Havana','calendar':'Lunes a viernes. Ajustar feriados y descansos pactados.','routine':[{'time':'08:30','action':'Revisar pedidos, vencimientos, novedades y documentos faltantes'},{'time':'09:00','action':'Ejecutar servicios priorizados y controles diarios'},{'time':'11:30','action':'Revisar cálculos, fuentes y resultados con responsables'},{'time':'14:00','action':'Atender clientes, propuestas y seguimiento comercial'},{'time':'16:00','action':'Registrar evidencia, replanificar y cerrar la jornada'}]}
    def ensure_tasks(self,day=None):
        day=day or today();month=day.strftime('%Y-%m');new=0
        with self.lock:
            known={(t.get('company_id'),t.get('service_id'),t.get('due')) for t in self.list('task')}
            for co in self.list('company'):
                if not co.get('contract_start') or not co.get('contract_end'):continue
                if not co['contract_start']<=day.isoformat()<=co['contract_end']:continue
                plan=self.plan({'company_id':co['id'],'month':month})
                for t in plan['tasks']:
                    key=(co['id'],t['service_id'],t['date'])
                    if key in known:continue
                    self.task({'title':f"S{t['service_id']:03d} · {t['service']}",'company_id':co['id'],'service_id':t['service_id'],'due':t['date'],'owner':co.get('owner','')});known.add(key);new+=1
        return {'date':day.isoformat(),'month':month,'created':new,'timezone':'America/Havana'}
    def task(self,p):
        if p.get('id'):obj=self.get(p['id'],'task');obj['status']=clean(p.get('status','Pendiente'));obj['evidence']=clean(p.get('evidence'),3000)
        else:
            if not p.get('title'):raise ValueError('Título obligatorio')
            if p.get('due'):date.fromisoformat(p['due'])
            obj={'id':uid('TAR'),'created_at':now(),'title':clean(p['title'],200),'company_id':p.get('company_id',''),'service_id':int(p.get('service_id',0)),'due':p.get('due',''),'owner':clean(p.get('owner'),150),'status':'Pendiente','evidence':''}
        if obj['status'] not in ('Pendiente','En curso','Completada','No aplica'):raise ValueError('Estado de tarea no válido')
        if obj['status'] in ('Completada','No aplica') and not obj['evidence']:raise ValueError('La tarea necesita evidencia o justificación')
        return self.save('task',obj,'tarea')
    def lead(self,p):
        if p.get('id'):
            obj=self.get(p['id'],'lead')
            for key in ('name','contact','need','source','stage','next_contact','owner','budget'):
                if key in p:obj[key]=clean(p[key],3000 if key=='need' else 200)
            return self.save('lead',obj,'seguimiento_prospecto')
        if not clean(p.get('name')) or not clean(p.get('need')):raise ValueError('Nombre y necesidad son obligatorios')
        obj={'id':uid('LEAD'),'created_at':now(),'name':clean(p['name'],150),'contact':clean(p.get('contact'),150),'need':clean(p['need'],3000),'source':clean(p.get('source','Manual'),100),'stage':clean(p.get('stage','Nuevo'),100),'next_contact':p.get('next_contact',''),'owner':clean(p.get('owner'),150),'budget':clean(p.get('budget'),100)}
        return self.save('lead',obj,'nuevo_prospecto')
    def elaborate(self,p):
        self.run(p);c=self.get(p['id'],'case');version=c['version'];co=self.get(c['company_id'],'company');docs=self.case_docs(c)
        result=self.ai.execute(c,co,docs,c['result'],self.norms_for(SERVICES[c['service_id']],co));latest=self.get(c['id'],'case')
        if latest['version']!=version:raise ValueError('Las entradas cambiaron durante la elaboración; repetir con la versión actual')
        latest['ai_result']=result;latest['agent_output']=result['text'];latest['approval']=None;latest['status']='En revisión';latest['version']+=1
        return self.save('case',latest,'elaboracion_ia')
    def answer(self,p):
        if not clean(p.get('question')):raise ValueError('Pregunta obligatoria')
        c=self.get(p['id'],'case');return self.ai.answer(c,self.case_docs(c),clean(p['question'],4000))
    def document_text(self,p):
        d=self.get(p['id'],'document')
        if not clean(p.get('text')):raise ValueError('Texto cotejado obligatorio')
        d['text']=clean(p['text'],2_000_000);d['characters']=len(d['text']);d['method']='Texto cotejado aportado por responsable';d['warnings']=['Cotejar con original de huella '+d['sha256']];self.save('document',d,'texto_cotejado')
        c=self.get(d['case_id'],'case');c['result']={};c['ai_result']=None;c['agent_output']='';c['approval']=None;c['status']='Recibido';c['version']+=1;self.save('case',c,'actualizar_fuente')
        return {'id':d['id'],'characters':d['characters']}
    def extract_again(self,p):
        d=self.get(p['id'],'document');r=extract(d['path']);return self.document_text({'id':d['id'],'text':r['text']})
    def dispatch(self,method,p):
        funcs={'ai_config':self.ai.configure,'ai_prepare':lambda p:self.ai.prepare(),'ai_models':lambda p:self.ai.models(),'elaborate':self.elaborate,'answer':self.answer,'document_text':self.document_text,'extract_again':self.extract_again,'company':self.company,'case':self.new_case,'upload':self.upload,'run':self.run,'update':self.update_case,'approve':self.approve,'deliver':self.deliver,'import':self.import_backup,'plan':self.plan,'task':self.task,'lead':self.lead}
        if method not in funcs:raise ValueError('Acción no disponible')
        return funcs[method](p)

TOOLS=[{'name':'buscar_servicios','description':'Buscar servicios por necesidad, ID o área. No modifica datos.','inputSchema':{'type':'object','properties':{'query':{'type':'string'}},'required':['query']}}, {'name':'consultar_expediente','description':'Consultar un expediente local con resultados y fuentes.','inputSchema':{'type':'object','properties':{'id':{'type':'string'}},'required':['id']}}, {'name':'listar_expedientes','description':'Listar expedientes de la oficina local.','inputSchema':{'type':'object','properties':{}}}, {'name':'procesar_expediente','description':'Ejecutar cálculo determinista y preparar un expediente; no aprueba ni envía.','inputSchema':{'type':'object','properties':{'id':{'type':'string'}},'required':['id']}}, {'name':'guardar_borrador','description':'Guardar resultado elaborado por el asistente para revisión humana.','inputSchema':{'type':'object','properties':{'id':{'type':'string'},'agent_output':{'type':'string'}},'required':['id','agent_output']}}, {'name':'planificar_mes','description':'Preparar el plan mensual de los servicios del contrato.','inputSchema':{'type':'object','properties':{'company_id':{'type':'string'},'month':{'type':'string'}},'required':['company_id','month']}}, {'name':'consultar_normas','description':'Consultar registro de fuentes oficiales; vigencia debe revalidarse al ejecutar.','inputSchema':{'type':'object','properties':{'topic':{'type':'string'}}}}]
def mcp_reply(office,msg):
    id_=msg.get('id');m=msg.get('method');p=msg.get('params',{})
    if id_ is None:return None
    result=None
    if m=='initialize':result={'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'oficina-inteligente-cuba','version':'1.0.0'}}
    elif m=='ping':result={}
    elif m=='tools/list':result={'tools':TOOLS}
    elif m=='tools/call':
        a=p.get('arguments') or {};name=p.get('name')
        try:
            if name=='buscar_servicios':data=[s for s in CATALOG if clean(a.get('query')).lower() in (str(s['id'])+' '+s['name']+' '+s['input_spec']).lower()]
            elif name=='consultar_expediente':data=office.get(a.get('id'),'case')
            elif name=='listar_expedientes':data=office.list('case')
            elif name=='procesar_expediente':data=office.run(a)
            elif name=='guardar_borrador':data=office.update_case(a)
            elif name=='planificar_mes':data=office.plan(a)
            elif name=='consultar_normas':data=[n for n in NORMS if not a.get('topic') or a['topic'] in n['topic']]
            else:raise ValueError('Herramienta desconocida')
            result={'content':[{'type':'text','text':json.dumps(data,ensure_ascii=False)}],'isError':False}
        except (ValueError,KeyError,TypeError) as e:result={'content':[{'type':'text','text':str(e)}],'isError':True}
    else:return {'jsonrpc':'2.0','id':id_,'error':{'code':-32601,'message':'Método no soportado'}}
    return {'jsonrpc':'2.0','id':id_,'result':result}

def serve(office,port,open_browser=False):
    token=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def send(self,content,status=200,mime='application/json',filename=None):
            if not isinstance(content,bytes):content=json.dumps(content,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(content)));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store')
            self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'")
            if filename:self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
            self.end_headers();self.wfile.write(content)
        def valid_host(self):return self.headers.get('Host','').split(':')[0] in ('localhost','127.0.0.1')
        def do_GET(self):
            if not self.valid_host():self.send({'error':'Host no permitido'},403);return
            u=urlparse(self.path);q=parse_qs(u.query)
            try:
                if u.path=='/api/state':self.send({**office.state(),'csrf':token});return
                if u.path=='/api/document':
                    d=office.get(q.get('id',[''])[0],'document');self.send({k:v for k,v in d.items() if k!='path'});return
                if u.path=='/api/backup':self.send(office.export_backup(),mime='application/json',filename='oficina-copia-privada.json');return
                if u.path=='/api/export':
                    blob,mime,name=office.export_case(q.get('id',[''])[0],q.get('format',['docx'])[0]);self.send(blob,mime=mime,filename=name);return
                relative='consola/index.html' if u.path=='/' else unquote(u.path).lstrip('/')
                if relative.startswith('assets/'):relative=relative[len('assets/'):]
                path=(ASSETS/relative).resolve()
                if ASSETS.resolve() not in path.parents or not path.is_file():self.send({'error':'Recurso no encontrado'},404);return
                import mimetypes
                self.send(path.read_bytes(),mime=mimetypes.guess_type(path)[0] or 'application/octet-stream')
            except (ValueError,KeyError) as e:self.send({'error':str(e)},400)
        def do_POST(self):
            if not self.valid_host():self.send({'error':'Host no permitido'},403);return
            origin=self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{port}',f'http://localhost:{port}'):self.send({'error':'Origen no permitido'},403);return
            if self.headers.get('X-Oficina-Token')!=token:self.send({'error':'Sesión local requerida'},403);return
            try:
                length=int(self.headers.get('Content-Length',0))
                if length<1 or length>280_000_000:raise ValueError('Tamaño de solicitud no permitido')
                p=json.loads(self.rfile.read(length));path=urlparse(self.path).path
                if not isinstance(p,dict):raise ValueError('Solicitud inválida')
                if path=='/mcp':
                    reply=mcp_reply(office,p);self.send(reply or {},status=200 if reply else 202);return
                method=path.removeprefix('/api/');self.send(office.dispatch(method,p))
            except (ValueError,KeyError,TypeError,zipfile.BadZipFile) as e:self.send({'error':str(e)},400)
            except Exception:self.send({'error':'No se pudo procesar el pedido. Revisar archivo, formato y dependencias.'},500)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'Oficina local: http://127.0.0.1:{port} · Ctrl+C para detener',flush=True)
    if open_browser:webbrowser.open(f'http://127.0.0.1:{port}')
    try:server.serve_forever()
    except KeyboardInterrupt:server.server_close()

def main():
    p=argparse.ArgumentParser(description='Oficina Inteligente Cuba — operaciones locales y ChatGPT')
    p.add_argument('--data-dir');sub=p.add_subparsers(dest='command',required=True)
    sp=sub.add_parser('serve');sp.add_argument('--port',type=int,default=8765);sp.add_argument('--open',action='store_true')
    daily=sub.add_parser('daily');daily.add_argument('--date');daily.add_argument('--output');sub.add_parser('mcp');sub.add_parser('state');sub.add_parser('catalog');e=sub.add_parser('extract');e.add_argument('path')
    calc=sub.add_parser('calculate');calc.add_argument('engine');calc.add_argument('--csv');calc.add_argument('--params',default='{}')
    act=sub.add_parser('action');act.add_argument('method');act.add_argument('--json');act.add_argument('--input')
    xp=sub.add_parser('export');xp.add_argument('id');xp.add_argument('--format',default='zip');xp.add_argument('--output',required=True)
    args=p.parse_args()
    if args.command=='catalog':print(json.dumps(CATALOG,ensure_ascii=False));return
    if args.command=='extract':print(json.dumps(extract(args.path),ensure_ascii=False));return
    if args.command=='calculate':print(json.dumps(calculate(args.engine,csv_rows(Path(args.csv).read_text(encoding='utf-8-sig')) if args.csv else [],json.loads(args.params)),ensure_ascii=False));return
    office=Office(args.data_dir)
    if args.command=='serve':serve(office,args.port,args.open)
    elif args.command=='mcp':
        for line in sys.stdin:
            try:
                reply=mcp_reply(office,json.loads(line))
                if reply:print(json.dumps(reply,ensure_ascii=False),flush=True)
            except Exception:print(json.dumps({'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'JSON inválido'}}),flush=True)
    elif args.command=='daily':
        day=date.fromisoformat(args.date) if args.date else today();summary=office.ensure_tasks(day);summary['tasks']=[t for t in office.list('task') if in_scope(t) and t.get('due') and t['due']<=day.isoformat() and t['status'] not in ('Completada','No aplica')];content=json.dumps(summary,ensure_ascii=False,indent=2)
        if args.output:Path(args.output).write_text(content,encoding='utf-8')
        else:print(content)
    elif args.command=='state':print(json.dumps(office.state(),ensure_ascii=False))
    elif args.command=='action':print(json.dumps(office.dispatch(args.method,read_json(args.input) if args.input else json.loads(args.json or '{}')),ensure_ascii=False))
    elif args.command=='export':Path(args.output).write_bytes(office.export_case(args.id,args.format)[0]);print(args.output)
if __name__=='__main__':main()
