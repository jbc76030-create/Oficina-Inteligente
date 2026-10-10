from pathlib import Path
from xml.sax.saxutils import escape
import io, csv, zipfile, json

def docx_bytes(title,body):
    paragraphs=[title]+str(body).splitlines()
    xml='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
    for i,line in enumerate(paragraphs):
        props='<w:pPr><w:spacing w:after="120"/></w:pPr>'
        run='<w:rPr><w:color w:val="073B4C"/><w:sz w:val="40"/><w:b/></w:rPr>' if i==0 else '<w:rPr><w:sz w:val="22"/></w:rPr>'
        xml+=f'<w:p>{props}<w:r>{run}<w:t xml:space="preserve">{escape(line)}</w:t></w:r></w:p>'
    xml+='<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1000" w:right="1000" w:bottom="1000" w:left="1000"/></w:sectPr></w:body></w:document>'
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr('_rels/.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr('word/document.xml',xml)
    return out.getvalue()
def report_text(case,service,company,docs,result,norms):
    lines=[f"EXPEDIENTE {case['id']}",f"Servicio S{service['id']:03d}: {service['name']}",f"Cliente: {company.get('name','sin identificar')} · {company.get('actor','por definir')}",f"Estado: {case['status']} · Versión: {case.get('version',1)}",f"Período: {case.get('period','por definir')}",'', 'PEDIDO',case.get('brief',''),'','FUENTES Y ENTRADAS']
    for d in docs:lines.append(f"{d['name']} · SHA256 {d['sha256']} · {len(d.get('text',''))} caracteres. Advertencias: {'; '.join(d.get('warnings',[]))}")
    lines+=['','RESULTADOS AUTOMÁTICOS',json.dumps(result.get('metrics',{}),ensure_ascii=False,indent=2),'']
    for w in result.get('warnings',[]):lines.append('Verificar: '+w)
    lines+=['','TRABAJO DEL ASISTENTE',case.get('agent_output') or 'Pendiente de elaboración en ChatGPT. El proceso local prepara y calcula; no simula una respuesta de inteligencia artificial.','', 'PROCEDIMIENTO ESPECIALIZADO']+service['steps']+['','FUENTES NORMATIVAS DE REFERENCIA']
    for n in norms:lines.append(f"{n['title']} · {n['locator']} · {n['url']} · Consulta {n['checked_at']}. Revisar aplicabilidad al caso.")
    lines+=['','REVISIÓN REQUERIDA']+service['quality']+['','MsC. Juan E. Badillo Castillo · WhatsApp 56955208 · jbcautonomo@gmail.com']
    return '\n'.join(lines)
def csv_bytes(rows):
    stream=io.StringIO();keys=list(dict.fromkeys(k for r in rows for k in r))
    writer=csv.DictWriter(stream,fieldnames=keys);writer.writeheader()
    for row in rows:
        safe={k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in row.items()}
        writer.writerow(safe)
    return ('\ufeff'+stream.getvalue()).encode('utf-8')
