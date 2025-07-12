# Disk Use Analyzer - Guía para Windows

Esta herramienta ahora es completamente compatible con Windows, macOS y Linux. Esta guía se enfoca en el uso en Windows.

## Requisitos

- Python 3.6 o superior
- Windows 10/11 (también funciona en Windows 7/8)
- Opcional: Docker Desktop para análisis de contenedores

## Instalación

1. **Verificar Python:**
   ```powershell
   python --version
   ```
   Si no tienes Python, descárgalo de [python.org](https://python.org)

2. **Clonar o descargar el repositorio:**
   ```powershell
   git clone <repository-url>
   cd Disk-Use-Analyzer
   ```

3. **Verificar la instalación:**
   ```powershell
   python disk_analyzer.py --help
   ```

## Uso Básico en Windows

### Analizar una unidad específica
```powershell
# Analizar unidad C:
python disk_analyzer.py C:\

# Analizar unidad D:
python disk_analyzer.py D:\

# Analizar carpeta específica
python disk_analyzer.py C:\Users\TuUsuario\Documents
```

### Analizar TODAS las unidades
```powershell
# Esta función analiza todas las unidades disponibles
python disk_analyzer.py --all-drives
```

### Análisis rápido (archivos > 50MB)
```powershell
python disk_analyzer.py C:\ --min-size 50
```

### Generar reporte HTML
```powershell
python disk_analyzer.py C:\ --html --export mi_reporte
```

## Características Específicas de Windows

### 1. Detección de Unidades
La herramienta detecta automáticamente todas las unidades montadas (C:, D:, E:, etc.)

### 2. Rutas de Cache de Windows
Analiza automáticamente:
- `%TEMP%` - Archivos temporales
- `%LOCALAPPDATA%\Temp` - Cache de aplicaciones
- `AppData\Local\Microsoft\Windows\INetCache` - Cache de Internet Explorer/Edge
- `AppData\Roaming\Code\Cache` - Cache de VS Code
- `$RECYCLE.BIN` - Papelera de reciclaje

### 3. Docker en Windows
Si tienes Docker Desktop instalado:
```powershell
python disk_analyzer.py --clean-docker
```

### 4. Comandos de Limpieza Adaptados
Los comandos de limpieza se adaptan a Windows:
- Usa `forfiles` en lugar de `find`
- Usa `del` y `rmdir` en lugar de `rm`
- Respeta las rutas con espacios

## Ejemplos de Uso

### Análisis completo con múltiples unidades
```powershell
# Analizar todas las unidades y generar reporte HTML
python disk_analyzer.py --all-drives --html --export analisis_completo

# Analizar solo archivos grandes en todas las unidades
python disk_analyzer.py --all-drives --min-size 100
```

### Limpieza segura
```powershell
# Ver qué se puede limpiar (sin borrar nada)
python disk_analyzer.py C:\ --clean-cache --dry-run

# Limpiar cache del sistema
python disk_analyzer.py C:\ --clean-cache

# Limpiar todo (cache + Docker)
python disk_analyzer.py C:\ --clean-all
```

### Análisis de carpetas específicas
```powershell
# Analizar descargas
python disk_analyzer.py %USERPROFILE%\Downloads

# Analizar archivos de programa
python disk_analyzer.py "C:\Program Files"

# Analizar proyectos de desarrollo
python disk_analyzer.py %USERPROFILE%\Documents\GitHub --min-size 10
```

## Uso con Makefile (Opcional)

Si tienes `make` instalado (viene con Git Bash o puedes usar [GnuWin32](http://gnuwin32.sourceforge.net/packages/make.htm)):

```bash
# Usar el Makefile multiplataforma
cp Makefile.cross-platform Makefile

# Comandos disponibles
make help           # Ver ayuda
make all-drives     # Analizar todas las unidades
make c-drive        # Analizar C:
make clean-preview  # Ver qué se puede limpiar
```

## Consejos para Windows

1. **Permisos de Administrador**: Para analizar carpetas del sistema como `C:\Windows` o `Program Files`, ejecuta PowerShell como Administrador.

2. **Rutas con Espacios**: La herramienta maneja automáticamente rutas con espacios. No necesitas comillas adicionales.

3. **Antivirus**: Algunos antivirus pueden ralentizar el análisis. Considera añadir una excepción temporal para `disk_analyzer.py`.

4. **Archivos del Sistema**: La herramienta ignora automáticamente archivos críticos como `pagefile.sys`, `hiberfil.sys`, y `swapfile.sys`.

## Solución de Problemas

### "Python no se reconoce como comando"
Añade Python al PATH durante la instalación o usa la ruta completa:
```powershell
C:\Python39\python.exe disk_analyzer.py C:\
```

### "Acceso denegado" en algunas carpetas
Ejecuta PowerShell como Administrador o ignora esas carpetas (la herramienta continúa con las demás).

### Docker no detectado
Asegúrate de que Docker Desktop esté instalado y en ejecución. La herramienta busca Docker en las ubicaciones estándar.

## Diferencias con macOS/Linux

- Usa barras invertidas (`\`) en las rutas
- Los comandos de limpieza usan sintaxis de Windows
- La papelera es `$RECYCLE.BIN` en lugar de `.Trash`
- Las aplicaciones están en `Program Files` en lugar de `/Applications`
- El directorio home es `%USERPROFILE%` en lugar de `~`

## Capturas de Pantalla

El reporte HTML generado incluye:
- Gráficos interactivos de uso de disco
- Visualización por categorías (Desarrollo, Docker, Sistema, etc.)
- Lista de archivos grandes con rutas completas
- Comandos de limpieza específicos para Windows

¡Disfruta liberando espacio en tu PC con Windows!