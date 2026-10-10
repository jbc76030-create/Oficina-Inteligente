"""Exporta productos del servicio; los formatos distinguen borrador y aprobación."""
import io,json,zipfile,html
from xml.sax.saxutils import escape
from entregables import docx_bytes
def final_text(c,s,co):
    return f"{s['name']}\n{co['name']} · {co['actor']}\nS{s['id']:03} · {c['id']} · v{c['version']} · {c['status']}\n\n"+(c.get('agent_output') or ('PAPEL DE CÁLCULO AUXILIAR\n'+json.dumps(c.get('result',{}).get('metrics',{}),ensure_ascii=False,indent=2)))+'\n\nREVISIÓN\n'+json.dumps(c.get('approval') or 'Pendiente',ensure_ascii=False)+'\n\nMsC. Juan E. Badillo Castillo · WhatsApp 56955208 · jbcautonomo@gmail.com'
def tables(c):
    out=list((c.get('ai_result') or {}).get('output',{}).get('tables',[]))
    rows=c.get('result',{}).get('rows',[])
    if rows:
        keys=list(dict.fromkeys(k for r in rows for k in r));out.append({'name':'Cálculo comprobable','columns':keys,'rows':[[r.get(k,'') for k in keys] for r in rows]})
    actions=(c.get('ai_result') or {}).get('output',{}).get('actions',[])
    if actions:out.append({'name':'Plan de acciones','columns':['Acción','Responsable','Fecha','Evidencia'],'rows':[[a[k] for k in ['action','owner','due','evidence']] for a in actions]})
    if not out:out=[{'name':'Resultado','columns':['Campo','Valor'],'rows':[[k,json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v] for k,v in c.get('result',{}).get('metrics',{}).items()]}]
    return out
def xlsx(c):
    ss=tables(c);files={};ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main';rel='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    files['[Content_Types].xml']='<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+''.join(f'<Override PartName="/xl/worksheets/sheet{i+1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(len(ss)))+'</Types>'
    files['_rels/.rels']=f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{rel}/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    names=[]
    for i,t in enumerate(ss):
        name=''.join(ch for ch in t['name'] if ch not in '[]:*?/\\')[:24] or 'Tabla'
        names.append(name+' '+str(i+1))
    files['xl/workbook.xml']=f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets>'+''.join(f'<sheet name="{escape(n)}" sheetId="{i+1}" r:id="rId{i+1}"/>' for i,n in enumerate(names))+'</sheets></workbook>'
    files['xl/_rels/workbook.xml.rels']='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i+1}" Type="{rel}/worksheet" Target="worksheets/sheet{i+1}.xml"/>' for i in range(len(ss)))+'</Relationships>'
    def col(n):
        s='';n+=1
        while n:n,r=divmod(n-1,26);s=chr(65+r)+s
        return s
    for i,t in enumerate(ss):
        rows=[]
        for k,row in enumerate([t['columns']]+t['rows']):
            cells=[]
            for j,v in enumerate(row):
                ref=col(j)+str(k+1)
                if isinstance(v,(float,int)):cells.append(f'<c r="{ref}"><v>{v}</v></c>')
                else:cells.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(str(v))}</t></is></c>')
            rows.append(f'<row r="{k+1}">'+''.join(cells)+'</row>')
        files[f'xl/worksheets/sheet{i+1}.xml']=f'<worksheet xmlns="{ns}"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" state="frozen"/></sheetView></sheetViews><sheetData>'+''.join(rows)+'</sheetData></worksheet>'
    return zip_bytes(files)
def client_html(c,s,co):
    text=html.escape(final_text(c,s,co))
    return ('<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(s['name'])+'</title><style>body{font:16px/1.7 Arial;color:#123742;background:#f5f1e8}main{max-width:1000px;margin:30px auto;padding:40px;background:white;border-top:7px solid #b96935}pre{font:inherit;white-space:pre-wrap}button{padding:12px;background:#073b4c;color:white;border:0}@media print{button{display:none}main{margin:0;padding:0;border:0}}</style><main><button onclick="window.print()">Imprimir / Guardar PDF</button><pre>'+text+'</pre></main></html>').encode()
def zip_bytes(files):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
    return stream.getvalue()
def export(c,s,co,kind):
    if not c.get('agent_output') and not c.get('result',{}).get('automated'):raise ValueError('Elaborar el producto antes de exportar')
    word=docx_bytes(s['name'],final_text(c,s,co));sheet=xlsx(c);web=client_html(c,s,co)
    if kind=='client_docx':return word,'application/vnd.openxmlformats-officedocument.wordprocessingml.document',c['id']+'-Entregable.docx'
    if kind=='xlsx':return sheet,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',c['id']+'-Tablas.xlsx'
    if kind=='html':return web,'text/html',c['id']+'-Entregable.html'
    if kind=='pptx':
        try:from pptx import Presentation
        except ImportError as e:raise ValueError('Instalar python-pptx o exportar la presentación desde la aplicación web') from e
        slides=(c.get('ai_result') or {}).get('output',{}).get('slides',[])
        if not slides:raise ValueError('Faltan diapositivas elaboradas')
        prs=Presentation()
        for sld in slides:
            slide=prs.slides.add_slide(prs.slide_layouts[1]);slide.shapes.title.text=sld['title'];slide.placeholders[1].text='\n'.join(sld['bullets']);slide.notes_slide.notes_text_frame.text=sld['notes']
        stream=io.BytesIO();prs.save(stream);return stream.getvalue(),'application/vnd.openxmlformats-officedocument.presentationml.presentation',c['id']+'-Presentacion.pptx'
    if kind=='client_zip':
        files={'Entregable.docx':word,'Tablas.xlsx':sheet,'Entregable.html':web,'Resultado-estructurado.json':json.dumps(c.get('ai_result') or c.get('result'),ensure_ascii=False,indent=2),'Revision.json':json.dumps({'status':c['status'],'version':c['version'],'approval':c.get('approval'),'quality':(c.get('ai_result') or {}).get('quality')},ensure_ascii=False,indent=2)}
        return zip_bytes(files),'application/zip',c['id']+'-Entrega-cliente.zip'
    raise ValueError('Formato de producto no válido')
