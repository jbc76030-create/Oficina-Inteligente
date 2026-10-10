# Transferir a otra cuenta

El complemento utiliza plugin.json y skills/oficina-inteligente-cuba/SKILL.md con recursos y scripts. Los paquetes se instalan desde un marketplace local/de repositorio en superficies compatibles. La interfaz disponible depende de cuenta y producto. Adjuntar un ZIP en un chat no equivale automáticamente a instalarlo.

En Codex copiar la habilidad a la carpeta admitida. En ChatGPT Work usar Habilidades/Plugins disponibles, o adjuntar el ZIP en Work y pedir extraer e instalar con validación y persistencia. Volver a autorizar conectores. No transferir tokens ni cookies.

Si la cuenta admite solo GPTs o Proyectos, usar instrucciones portables y archivos de conocimiento. Esa ruta no instala un backend ni activa herramientas ausentes. Habilitar análisis de archivos y navegación cuando estén disponibles.

## Expedientes

La distribución no incluye clientes reales. Exportar copia privada si se necesita trasladarlos; importar crea IDs nuevos, conserva vínculos y comprueba SHA256. No publicar copias en la web. El ZIP por expediente incluye pedido, originales, resultados, instrucciones y Word; adjuntarlo a ChatGPT, guardar el resultado como borrador y revisar.

## Verificar la instalación

1. Comprobar 144 servicios, 27 áreas y 19 roles.
2. Ejemplo costos: fijo 10000, precio 100, variable 60, unidades 400 → resultado 6000, equilibrio 250 unidades.
3. Crear cliente/pedido, cargar CSV, procesar y exportar Word.
4. Exportar/importar copia de ejemplo y cotejar vínculos y huellas.
5. Consultar norma oficial y comprobar herramientas de la nueva cuenta.

## Compatibilidad oficial

https://developers.openai.com/plugins/build/plugins
https://developers.openai.com/plugins/build/skills
https://developers.openai.com/plugins/concepts/skills
https://developers.openai.com/api/docs/guides/tools-skills

Consultado el 10/10/2026. No se incluye un App ID ni conexión remota inventada. El MCP opcional se inicia con python scripts/oficina.py mcp en entorno stdio compatible. ChatGPT remoto requiere HTTPS, autenticación y registro.
