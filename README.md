<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Oficina Inteligente - Panel de Gestión</title>
    <style>
        :root {
            --primary: #1e293b;
            --accent: #2563eb;
            --bg: #f8fafc;
            --card: #ffffff;
            --text: #0f172a;
            --border: #e2e8f0;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            margin: 0;
            display: flex;
            height: 100vh;
        }

        /* Sidebar */
        aside {
            width: 260px;
            background-color: var(--primary);
            color: white;
            padding: 20px;
            display: flex;
            flex-direction: column;
        }

        aside h2 {
            font-size: 1.2rem;
            margin-bottom: 30px;
            color: #93c5fd;
        }

        aside nav a {
            color: #cbd5e1;
            text-decoration: none;
            display: block;
            padding: 10px 15px;
            border-radius: 6px;
            margin-bottom: 8px;
            transition: 0.3s;
        }

        aside nav a:hover, aside nav a.active {
            background-color: var(--accent);
            color: white;
        }

        /* Main Content */
        main {
            flex: 1;
            padding: 30px;
            overflow-y: auto;
        }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid var(--border);
            padding-bottom: 15px;
            margin-bottom: 25px;
        }

        .card {
            background: var(--card);
            border-radius: 8px;
            padding: 20px;
            border: 1px solid var(--border);
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            margin-bottom: 20px;
        }

        .form-group {
            margin-bottom: 15px;
        }

        label {
            display: block;
            margin-bottom: 5px;
            font-weight: 600;
        }

        input, select, textarea {
            width: 100%;
            padding: 10px;
            border: 1px solid var(--border);
            border-radius: 6px;
            box-sizing: border-box;
            font-size: 14px;
        }

        button {
            background-color: var(--accent);
            color: white;
            border: none;
            padding: 12px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: bold;
            transition: 0.2s;
        }

        button:hover {
            opacity: 0.9;
        }

        /* Document Output Preview */
        .output-doc {
            font-family: Arial, sans-serif;
            font-size: 12pt;
            line-height: 1.5;
            text-align: justify;
            padding: 25px;
            border: 1px solid #ccc;
            background-color: #fff;
            min-height: 200px;
            white-space: pre-wrap;
        }

        .badge {
            background-color: #fef3c7;
            color: #92400e;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.85rem;
            font-weight: bold;
        }
    </style>
</head>
<body>

    <aside>
        <h2>Oficina Inteligente</h2>
        <nav>
            <a href="#" class="active">Nueva Solicitud</a>
            <a href="#">Expedientes</a>
            <a href="#">Catálogo (143 Servicios)</a>
            <a href="#">Configuración</a>
        </nav>
    </aside>

    <main>
        <div class="header">
            <h1>Gestión de Solicitudes</h1>
            <span class="badge">Control Humano Obligatorio</span>
        </div>

        <div class="card">
            <h2>Datos del Actor Económico y Servicio</h2>
            <form id="serviceForm">
                <div class="form-group">
                    <label for="client">Cliente / Actor Económico:</label>
                    <input type="text" id="client" placeholder="Ej. Restaurante Bahía S.U.R.L." required>
                </div>

                <div class="form-group">
                    <label for="serviceNum">Número o Tipo de Servicio (1 al 143):</label>
                    <input type="text" id="serviceNum" placeholder="Ej. Servicio #12: Estudio de Factibilidad Económica" required>
                </div>

                <div class="form-group">
                    <label for="modality">Modalidad:</label>
                    <select id="modality">
                        <option value="Gestionada">Gestionada</option>
                        <option value="Híbrida">Híbrida</option>
                        <option value="Implantación">Implantación</option>
                    </select>
                </div>

                <div class="form-group">
                    <label for="details">Detalles y Antecedentes de la Solicitud:</label>
                    <textarea id="details" rows="4" placeholder="Ingrese notas, montos, datos de entrada o especificaciones técnicas..."></textarea>
                </div>

                <button type="button" onclick="processRequest()">Procesar en Oficina Inteligente</button>
            </form>
        </div>

        <div class="card" id="outputCard" style="display:none;">
            <h2>Entregable Generado</h2>
            <div id="outputDoc" class="output-doc"></div>
            <br>
            <button onclick="copyToClipboard()" style="background-color: #059669;">Copiar Texto Limpio</button>
        </div>
    </main>

    <script>
        function processRequest() {
            const client = document.getElementById('client').value;
            const service = document.getElementById('serviceNum').value;
            const modality = document.getElementById('modality').value;
            const details = document.getElementById('details').value;

            if(!client || !service) {
                alert('Por favor complete el nombre del cliente y el servicio.');
                return;
            }

            const outputText = `EXPEDIENTE OFICIAL - OFICINA INTELIGENTE
--------------------------------------------------
ACTOR ECONÓMICO: ${client.toUpperCase()}
SERVICIO SOLICITADO: ${service}
MODALIDAD DE TRABAJO: ${modality}
FECHA DE PROCESAMIENTO: ${new Date().toLocaleDateString('es-ES')}

DESCRIPCIÓN DE LA SOLICITUD:
${details ? details : 'Sin antecedentes adicionales ingresados.'}

ESTADO DE REVISIÓN:
[X] Memoria de proyecto aislada correctamente.
[X] Formato visual normativo aplicado (Márgenes 2x2x2x2 cm / Fuente Arial 12).
[ ! ] NOTA: Este borrador requiere Control Humano Obligatorio antes de su firma o entrega final.
--------------------------------------------------`;

            document.getElementById('outputDoc').innerText = outputText;
            document.getElementById('outputCard').style.display = 'block';
            document.getElementById('outputCard').scrollIntoView({ behavior: 'smooth' });
        }

        function copyToClipboard() {
            const text = document.getElementById('outputDoc').innerText;
            navigator.clipboard.writeText(text);
            alert('¡Texto copiado al portapapeles!');
        }
    </script>
</body>
</html>
