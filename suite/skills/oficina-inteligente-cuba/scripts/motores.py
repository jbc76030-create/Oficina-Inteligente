"""Cálculos reproducibles y extracción local. No invoca modelos ni acciones externas."""
from __future__ import annotations
import csv, io, json, re, zipfile, hashlib, subprocess, shutil
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree as ET
import unicodedata

NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def norm(s):return ''.join(c for c in unicodedata.normalize('NFD',str(s).lower().strip()) if unicodedata.category(c)!='Mn').replace(' ','_')
def money(v):
    if v is None or str(v).strip()=='':return Decimal('0')
    s=str(v).strip().replace(' ','').replace('$','')
    if ',' in s and '.' in s:s=s.replace(',','') if s.rfind('.')>s.rfind(',') else s.replace('.','').replace(',','.')
    elif ',' in s:s=s.replace(',','.')
    try:
        d=Decimal(s)
        if not d.is_finite():raise ValueError('Importe no finito')
        return d
    except InvalidOperation:raise ValueError('Importe inválido: '+str(v)[:40])
def rounded(d):return float(Decimal(d).quantize(Decimal('.01')))
def num(r,*keys,default=0):
    for k in keys:
        if k in r and str(r[k]).strip()!='':return money(r[k])
    return money(default)
def csv_rows(text):
    if not text.strip():return []
    try:dialect=csv.Sniffer().sniff(text[:5000],delimiters=',;\t')
    except csv.Error:dialect=csv.excel
    rows=list(csv.DictReader(io.StringIO(text),dialect=dialect))
    if len(rows)>50000:raise ValueError('Máximo 50000 filas por archivo')
    return [{norm(k):v.strip() if isinstance(v,str) else v for k,v in r.items() if k is not None} for r in rows]
def xlsx_text(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        if sum(i.file_size for i in z.infolist())>80_000_000:raise ValueError('XLSX demasiado grande al descomprimir')
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            strings=[''.join(si.itertext()) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        ws=sorted(n for n in z.namelist() if re.match(r'xl/worksheets/sheet\d+\.xml$',n))
        if not ws:return '',[]
        output=io.StringIO();writer=csv.writer(output)
        for row in ET.fromstring(z.read(ws[0])).findall('.//m:row',NS):
            vals={}
            for c in row.findall('m:c',NS):
                letters=re.match('[A-Z]+',c.attrib.get('r','A1'))[0];col=0
                for x in letters:col=col*26+ord(x)-64
                v=c.find('m:v',NS);text=v.text if v is not None else ''
                if c.attrib.get('t')=='s':text=strings[int(text)] if text else ''
                if c.attrib.get('t')=='inlineStr':text=''.join(c.find('m:is',NS).itertext())
                vals[col-1]=text or ''
            writer.writerow([vals.get(i,'') for i in range(max(vals,default=-1)+1)])
        return output.getvalue(),['Se extrae la primera hoja; las fórmulas usan el valor guardado. Recalcular el original si cambió.']
def extract(path):
    path=Path(path);blob=path.read_bytes();ext=path.suffix.lower();warnings=[]
    if len(blob)>25_000_000:raise ValueError('Máximo 25 MB por documento')
    if ext in ('.txt','.csv','.md','.json','.tsv'):
        try:text=blob.decode('utf-8-sig')
        except UnicodeDecodeError:text=blob.decode('cp1252');warnings.append('Codificación interpretada como Windows-1252.')
    elif ext=='.docx':
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            if sum(i.file_size for i in z.infolist())>80_000_000:raise ValueError('DOCX demasiado grande al descomprimir')
            tree=ET.fromstring(z.read('word/document.xml'));ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            text='\n'.join(''.join(p.itertext()) for p in tree.findall('.//w:p',ns))
        warnings.append('Texto y tablas extraídos; revisar formato, notas y elementos gráficos en el original.')
    elif ext=='.xlsx':text,warnings=xlsx_text(blob)
    elif ext=='.pdf':
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                if len(pdf.pages)>1000:raise ValueError('Máximo 1000 páginas')
                text='\n'.join(f'[Página {i+1}]\n'+(p.extract_text() or '') for i,p in enumerate(pdf.pages))
        except ImportError:
            if not shutil.which('pdftotext'):return {'text':'','warnings':['Para PDF instalar pdfplumber o Poppler; aportar texto si no están disponibles.'],'sha256':hashlib.sha256(blob).hexdigest(),'method':'pendiente'}
            text=subprocess.run(['pdftotext','-layout',str(path),'-'],capture_output=True,text=True,check=True,timeout=90).stdout
        warnings.append('PDF: verificar orden de columnas y legibilidad. Los escaneos pueden necesitar OCR.')
    elif ext in ('.png','.jpg','.jpeg','.webp'):
        if shutil.which('tesseract'):
            text=subprocess.run(['tesseract',str(path),'stdout','-l','spa+eng'],capture_output=True,text=True,timeout=90).stdout
            if not text.strip():text=subprocess.run(['tesseract',str(path),'stdout','-l','eng'],capture_output=True,text=True,timeout=90).stdout
            warnings.append('OCR: cotejar nombres, números e importes con la imagen original.')
        else:text='';warnings.append('OCR no disponible: aportar transcripción revisada o procesar la imagen en ChatGPT.')
    else:raise ValueError('Formato permitido: PDF, DOCX, XLSX, CSV, TXT, MD, JSON, PNG, JPG o WEBP')
    return {'text':text[:2_000_000],'warnings':warnings,'sha256':hashlib.sha256(blob).hexdigest(),'method':'extracción local','characters':len(text)}

def calculate(engine,rows,params=None):
    p=params or {};rows=[{norm(k):v for k,v in r.items()} for r in rows];metrics={};table=[];warnings=[];by={}
    if engine in ('finanzas','conciliacion'):
        if engine=='conciliacion' and rows and all('fuente' in r for r in rows):
            bank=[r for r in rows if norm(r.get('fuente')) in ('banco','bank')];books=[r for r in rows if norm(r.get('fuente')) in ('libro','contabilidad','books')]
            if len(bank)+len(books)!=len(rows):raise ValueError('fuente debe ser banco o libro')
            keys=lambda r:(str(r.get('referencia','')).strip(),str(r.get('moneda',p.get('moneda','CUP'))).upper(),num(r,'importe'))
            def mapped(seq):
                m=defaultdict(list)
                for r in seq:
                    if not r.get('referencia'):raise ValueError('Conciliación: falta referencia')
                    m[keys(r)].append(r)
                return m
            b,l=mapped(bank),mapped(books);matched=0
            for key in sorted(b.keys()|l.keys(),key=lambda k:(k[0],k[1],k[2])):
                nb,nl=len(b.get(key,[])),len(l.get(key,[]));n=min(nb,nl);matched+=n
                table.append({'referencia':key[0],'moneda':key[1],'importe':rounded(key[2]),'banco':nb,'libro':nl,'pareadas':n,'pendientes_banco':nb-n,'pendientes_libro':nl-n})
            metrics={'filas_banco':len(bank),'filas_libro':len(books),'operaciones_pareadas':matched,'pendientes_banco':len(bank)-matched,'pendientes_libro':len(books)-matched}
            warnings.append('Pareado por referencia, moneda e importe con multiplicidad. Las fechas y partidas pendientes requieren cotejo; no se certifica el saldo contable.')
        else:
            expected=('credito','debito','ingreso','gasto','importe')
            if rows and not any(any(k in r for k in expected) for r in rows):raise ValueError('Se necesitan columnas credito/debito, ingreso/gasto o importe firmado')
            groups=defaultdict(list)
            for r in rows:groups[str(r.get('moneda',p.get('moneda','CUP'))).upper()].append(r)
            for currency,group in groups.items():
                credits=Decimal(0);debits=Decimal(0);counts=Counter();balance=money(p.get('saldo_inicial',0));ordered=sorted(group,key=lambda r:str(r.get('fecha','')))
                for i,r in enumerate(ordered):
                    if 'importe' in r and not any(k in r for k in ('credito','debito','ingreso','gasto')):
                        v=num(r,'importe');c=max(v,Decimal(0));d=max(-v,Decimal(0))
                    else:c=num(r,'credito','ingreso');d=num(r,'debito','gasto')
                    if c.quantize(Decimal('.01'))!=c or d.quantize(Decimal('.01'))!=d:raise ValueError('Importes bancarios: máximo 2 decimales')
                    if c<0 or d<0:raise ValueError('Crédito y débito deben ser no negativos; usar importe firmado para valores con signo')
                    credits+=c;debits+=d;balance+=c-d
                    signature=(str(r.get('referencia','')),str(r.get('fecha','')),c,d)
                    counts[signature]+=1
                    table.append({'fecha':r.get('fecha',''),'referencia':r.get('referencia',''),'concepto':r.get('concepto',''),'moneda':currency,'credito':rounded(c),'debito':rounded(d),'saldo_calculado':rounded(balance)})
                by[currency]={'ingresos':rounded(credits),'egresos':rounded(debits),'flujo_neto':rounded(credits-debits),'saldo_inicial':rounded(money(p.get('saldo_inicial',0))),'saldo_calculado':rounded(balance),'duplicados_potenciales':sum(v-1 for k,v in counts.items() if v>1 and k[0])}
            metrics={'movimientos':len(rows),'por_moneda':by}
            warnings.append('No se agregan distintas monedas. Las repeticiones solo son candidatos; no se eliminan ni prueban fraude.')
            if len(groups)>1 and money(p.get('saldo_inicial',0))!=0:raise ValueError('Con varias monedas, usar saldo inicial cero o procesar cada moneda por separado')
    elif engine=='costos':
        fixed=money(p.get('costos_fijos',0));price=money(p.get('precio',0));variable=money(p.get('costo_variable',0));quantity=money(p.get('unidades',0));contribution=price-variable
        if min(fixed,price,variable,quantity)<0:raise ValueError('Costos, precio y unidades deben ser no negativos')
        metrics={'costos_fijos':rounded(fixed),'precio':rounded(price),'costo_variable_unitario':rounded(variable),'margen_contribucion_unitario':rounded(contribution),'unidades':rounded(quantity),'ingresos':rounded(price*quantity),'costo_total':rounded(fixed+variable*quantity),'resultado_operativo':rounded(contribution*quantity-fixed),'punto_equilibrio_unidades':rounded(fixed/contribution) if contribution>0 else None,'margen_sobre_precio_pct':rounded(contribution/price*100) if price else None}
        if contribution<=0:warnings.append('No hay punto de equilibrio finito: la contribución unitaria no es positiva.')
    elif engine=='presupuesto':
        for r in rows:
            if not any(k in r for k in ('plan','presupuesto')) or not any(k in r for k in ('ejecutado','real')):raise ValueError('Presupuesto: faltan plan y ejecutado')
            plan=num(r,'plan','presupuesto');used=num(r,'ejecutado','real');commit=num(r,'comprometido');cur=r.get('moneda',p.get('moneda','CUP'))
            table.append({'partida':r.get('partida',r.get('concepto','')),'moneda':cur,'plan':rounded(plan),'ejecutado':rounded(used),'comprometido':rounded(commit),'saldo_disponible':rounded(plan-used-commit),'desviacion':rounded(used-plan),'ejecucion_pct':rounded(used/plan*100) if plan else None})
        metrics={'partidas':len(table),'partidas_con_sobreejecucion':sum(r['saldo_disponible']<0 for r in table)}
    elif engine=='riesgos':
        for r in rows:
            prob=num(r,'probabilidad');impact=num(r,'impacto')
            if not (1<=prob<=5 and 1<=impact<=5):raise ValueError('Probabilidad e impacto deben estar entre 1 y 5')
            score=prob*impact
            table.append({'riesgo':r.get('riesgo',''),'probabilidad':float(prob),'impacto':float(impact),'valor':float(score),'prioridad':'Alta' if score>=15 else 'Media' if score>=6 else 'Baja','control':r.get('control',''),'responsable':r.get('responsable',''),'evidencia':r.get('evidencia','')})
        table.sort(key=lambda r:r['valor'],reverse=True);metrics={'riesgos':len(table),'prioridad_alta':sum(r['prioridad']=='Alta' for r in table)}
        warnings.append('Escala operativa propuesta 1–5. No es una clasificación legal ni un diagnóstico técnico certificado.')
    elif engine=='inventario':
        for r in rows:
            if not all(k in r for k in ('libros','fisico')):raise ValueError('Inventario: faltan libros y fisico')
            books=num(r,'libros');physical=num(r,'fisico');cost=num(r,'costo_unitario');minimum=num(r,'minimo');diff=physical-books
            table.append({'articulo':r.get('articulo',''),'moneda':r.get('moneda','CUP'),'libros':float(books),'fisico':float(physical),'diferencia':float(diff),'valor_diferencia':rounded(diff*cost),'reposicion':physical<minimum,'custodio':r.get('custodio','')})
        metrics={'articulos':len(table),'diferencias':sum(r['diferencia']!=0 for r in table),'alertas_reposicion':sum(r['reposicion'] for r in table)}
    elif engine=='compras':
        for r in rows:
            table.append({'proveedor':r.get('proveedor',''),'moneda':r.get('moneda','CUP'),'precio':rounded(num(r,'precio')),'dias_entrega':float(num(r,'dias_entrega')),'garantia':r.get('garantia',''),'cumple_especificacion':r.get('cumple_especificacion','por verificar')})
        table.sort(key=lambda r:(r['moneda'],r['precio']));metrics={'ofertas':len(table)};warnings.append('Orden por precio dentro de cada moneda. Verificar especificaciones y criterios; no constituye adjudicación.')
    elif engine=='proyecto':
        for r in rows:
            physical=num(r,'avance_fisico_pct');planned=num(r,'avance_plan_pct');budget=num(r,'presupuesto');used=num(r,'ejecutado')
            if not (0<=physical<=100 and 0<=planned<=100):raise ValueError('Avances deben estar entre 0 y 100')
            financial=used/budget*100 if budget else None
            table.append({'hito':r.get('hito',''),'moneda':r.get('moneda','CUP'),'avance_fisico_pct':float(physical),'avance_plan_pct':float(planned),'desviacion_fisica_pp':float(physical-planned),'presupuesto':rounded(budget),'ejecutado':rounded(used),'avance_financiero_pct':rounded(financial) if financial is not None else None,'responsable':r.get('responsable','')})
        metrics={'hitos':len(table),'hitos_retrasados':sum(r['desviacion_fisica_pp']<0 for r in table)}
    elif engine=='variaciones':
        for r in rows:
            if 'real' not in r or 'referencia' not in r:raise ValueError('Variaciones: faltan real y referencia numérica')
            real=num(r,'real');ref=num(r,'referencia');delta=real-ref
            table.append({'concepto':r.get('concepto',''),'moneda':r.get('moneda','CUP'),'real':rounded(real),'referencia':rounded(ref),'variacion':rounded(delta),'variacion_pct':rounded(delta/abs(ref)*100) if ref else None})
        metrics={'partidas':len(table),'bases_cero':sum(r['referencia']==0 for r in table)}
        warnings.append('Variación porcentual sobre valor absoluto de referencia. Las causas requieren evidencia.')
    elif engine=='contabilidad':
        if rows and not all('debe' in r and 'haber' in r for r in rows):raise ValueError('Contabilidad: columnas debe y haber obligatorias')
        groups=defaultdict(list)
        for r in rows:groups[r.get('moneda','CUP')].append(r)
        checks={}
        for cur,group in groups.items():
            d=sum((num(r,'debe') for r in group),Decimal(0));h=sum((num(r,'haber') for r in group),Decimal(0))
            if any(num(r,'debe')<0 or num(r,'haber')<0 for r in group):raise ValueError('Debe y haber deben ser no negativos')
            checks[cur]={'debe':rounded(d),'haber':rounded(h),'diferencia':rounded(d-h)}
        counts=Counter(tuple(sorted(r.items())) for r in rows)
        metrics={'filas':len(rows),'por_moneda':checks,'filas_repetidas_potenciales':sum(n-1 for n in counts.values() if n>1)};table=rows
        warnings.append('Solo controles de cuadre y repeticiones; no genera estados, asientos ni certificación contable.')
    elif engine=='indicadores':
        for r in rows:
            if 'real' not in r or 'meta' not in r:raise ValueError('Indicadores: real y meta obligatorios')
            real=num(r,'real');meta=num(r,'meta');direction=norm(r.get('sentido','mayor'))
            if direction not in ('mayor','menor'):raise ValueError('Sentido debe ser mayor o menor')
            table.append({'indicador':r.get('indicador',''),'unidad':r.get('unidad',''),'real':float(real),'meta':float(meta),'sentido':direction,'cumple':real>=meta if direction=='mayor' else real<=meta,'desviacion':float(real-meta),'fuente':r.get('fuente','')})
        metrics={'indicadores':len(table),'metas_cumplidas':sum(r['cumple'] for r in table)}
        warnings.append('Metas aportadas por el cliente; verificar fórmula, período y fuente de cada indicador.')
    elif engine=='tiempos':
        saved=Decimal(0)
        for r in rows:
            if not all(k in r for k in ('minutos_base','minutos_actuales','volumen')):raise ValueError('Tiempos: minutos_base, minutos_actuales y volumen obligatorios')
            base=num(r,'minutos_base');actual=num(r,'minutos_actuales');volume=num(r,'volumen')
            if min(base,actual,volume)<0:raise ValueError('Tiempos y volumen deben ser no negativos')
            delta=(base-actual)*volume;saved+=delta
            table.append({'tarea':r.get('tarea',''),'minutos_base':float(base),'minutos_actuales':float(actual),'volumen':float(volume),'minutos_ahorrados':float(delta),'horas_ahorradas':rounded(delta/60),'evidencia':r.get('evidencia','')})
        metrics={'tareas':len(table),'minutos_ahorrados':float(saved),'horas_ahorradas':rounded(saved/60)}
        warnings.append('Ahorro del volumen informado; no extrapolar a meses ni convertirlo en resultado probado sin evidencia comparable de tiempos y calidad.')
    elif engine=='cotizacion':
        totals=defaultdict(Decimal)
        for r in rows:
            required=('volumen','frecuencia','minutos_unitarios','costo_hora')
            if not all(k in r for k in required):raise ValueError('Cotización: volumen, frecuencia, minutos_unitarios y costo_hora obligatorios')
            volume=num(r,'volumen');freq=num(r,'frecuencia');minutes=num(r,'minutos_unitarios');hour=num(r,'costo_hora');extra=num(r,'costos_herramientas');margin=num(r,'recargo_pct')
            if min(volume,freq,minutes,hour,extra,margin)<0:raise ValueError('Parámetros de cotización no negativos')
            cost=volume*freq*minutes/60*hour+extra;price=cost*(1+margin/100);cur=r.get('moneda','CUP');totals[cur]+=price
            table.append({'servicio':r.get('servicio',''),'moneda':cur,'horas':rounded(volume*freq*minutes/60),'costo':rounded(cost),'recargo_pct':float(margin),'precio_propuesto':rounded(price)})
        metrics={'lineas':len(table),'precio_por_moneda':{k:rounded(v) for k,v in totals.items()}}
        warnings.append('Recargo sobre costo, no margen sobre venta. Carga, tarifas y herramientas aportadas; tributos y condiciones se validan aparte.')
    elif engine=='datos':
        metrics={'filas':len(rows),'columnas':len(rows[0]) if rows else 0,'celdas_vacias':sum(v is None or str(v).strip()=='' for r in rows for v in r.values()),'filas_repetidas_potenciales':sum(n-1 for n in Counter(tuple(sorted(r.items())) for r in rows).values() if n>1)};table=rows
    return {'engine':engine,'metrics':metrics,'rows':table,'warnings':warnings,'automated':bool(metrics)}

def cadence(s):
    daily={19,20,26,27,44,47,65,66,76,79,84,91,110,113,115,117,120,135}
    weekly={23,24,25,29,33,35,43,46,48,49,57,61,72,73,77,97,99,100,103,105,106,108,111,112,114,116,119,121,122,136,138,139,140}
    monthly={6,7,9,15,28,30,31,32,34,36,37,38,39,40,41,42,45,50,51,52,53,54,55,58,59,60,62,67,69,70,71,74,75,78,80,81,82,85,87,88,90,92,93,94,95,96,98,101,102,107,109,125,126,127,130,131,132,133,134,137,141,142,143,144}
    return 'Diaria' if s['id'] in daily else 'Semanal' if s['id'] in weekly else 'Mensual' if s['id'] in monthly else 'Bajo demanda'
def monthly_plan(services,year,month,start=None,end=None):
    first=date(year,month,1);last=(date(year+1,1,1) if month==12 else date(year,month+1,1))-timedelta(days=1)
    active_start=max(first,date.fromisoformat(start)) if start else first
    active_end=min(last,date.fromisoformat(end)) if end else last
    days=[first+timedelta(days=i) for i in range((last-first).days+1) if (first+timedelta(days=i)).weekday()<5 and active_start<=first+timedelta(days=i)<=active_end]
    plan=[]
    for idx,s in enumerate(services):
        freq=cadence(s);target=days[-1] if days else None
        if not target:continue
        if freq=='Diaria':dates=days
        elif freq=='Semanal':dates=[d for d in days if d.weekday()==4];dates=dates or [days[-1]]
        else:dates=[days[min(len(days)-1,(s['area']-1)*len(days)//27)]]
        for d in dates:plan.append({'service_id':s['id'],'service':s['name'],'date':d.isoformat(),'cadence':freq,'action':'Comprobar demanda y evidencias; ejecutar si procede' if freq=='Bajo demanda' else 'Validar entradas, ejecutar/controlar y revisar evidencia','agent':s['agent'],'status':'Pendiente','evidence':'','monthly_control':target.isoformat()})
    return sorted(plan,key=lambda r:(r['date'],r['service_id']))
