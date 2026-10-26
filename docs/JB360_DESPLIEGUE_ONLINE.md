# JB360: plan de despliegue web (piloto)

**Estado: preparación; NO publicado.** Esta rama contiene solo el plan, no datos de clientes, contraseñas ni código del servidor.

## Arquitectura propuesta
- Página comercial existente: GitHub Pages, sin credenciales ni datos internos.
- Aplicación privada: servicio Python/FastAPI con URL HTTPS independiente.
- Persistencia: base de datos gestionada o almacenamiento persistente con copias y pruebas de restauración. SQLite local efímero NO es aceptable para producción.
- Acceso: cuentas individuales, contraseñas exclusivas, sesiones con vencimiento, limitación de intentos, restablecimiento seguro y auditoría.
- Administración: acceso restringido; secretos exclusivamente en variables de entorno del alojamiento, nunca en GitHub.
- Dispositivos: interfaz web adaptable para Windows, Android, iOS y tabletas.

## Bloqueantes antes de publicar
1. Revisar y corregir autenticación, expiración/revocación de tokens y control de intentos.
2. Garantizar persistencia y recuperación de datos; probar copias y restauración.
3. Configurar dominio/URL HTTPS y proveedor de alojamiento con el titular de la cuenta.
4. Ejecutar pruebas de extremo a extremo y en navegadores móviles.
5. Separar explícitamente el módulo operativo piloto de cualquier declaración fiscal oficial: NO certificado.
6. Publicar primero en entorno de pruebas con datos ficticios y acceso limitado.

## Próximos pasos
- Crear repositorio PRIVADO para el backend de JB360.
- Elegir alojamiento que soporte Python y almacenamiento persistente.
- Configurar variables de entorno y credenciales nuevas.
- Desplegar entorno de pruebas y verificar accesos desde dispositivos.
- Aprobar salida a producción solo tras superar las pruebas.

**Nunca colocar claves ni bases de datos de usuarios en este repositorio público.**
