# Makefile para macOS Disk Analyzer
# Uso: make [comando]

# Variables
PYTHON = python3
SCRIPT = disk_analyzer.py
DEFAULT_PATH = ~/
MIN_SIZE = 10
TIMESTAMP := $(shell date +%Y%m%d_%H%M%S)
REPORT_NAME = disk_report_$(TIMESTAMP)

# Colores para output
RED = \033[0;31m
GREEN = \033[0;32m
YELLOW = \033[1;33m
BLUE = \033[0;34m
NC = \033[0m # No Color

# Comandos principales
.PHONY: help analyze quick full report clean-preview clean-cache clean-docker clean-all install gui install-gui check-gui web install-web

help:
	@echo "$(BLUE)═══════════════════════════════════════════════════════════════$(NC)"
	@echo "$(BLUE)            macOS Disk Analyzer - Comandos Disponibles$(NC)"
	@echo "$(BLUE)═══════════════════════════════════════════════════════════════$(NC)"
	@echo ""
	@echo "$(GREEN)Análisis:$(NC)"
	@echo "  $(YELLOW)make analyze$(NC)      - Análisis estándar del directorio home"
	@echo "  $(YELLOW)make quick$(NC)        - Análisis rápido (archivos > 50MB)"
	@echo "  $(YELLOW)make full$(NC)         - Análisis completo con reporte HTML"
	@echo "  $(YELLOW)make report$(NC)       - Solo generar reporte HTML del último análisis"
	@echo ""
	@echo "$(GREEN)Limpieza:$(NC)"
	@echo "  $(YELLOW)make clean-preview$(NC) - Ver qué se puede limpiar (dry-run)"
	@echo "  $(YELLOW)make clean-cache$(NC)   - Limpiar cache del sistema"
	@echo "  $(YELLOW)make clean-docker$(NC)  - Limpiar recursos Docker"
	@echo "  $(YELLOW)make clean-all$(NC)     - Limpiar todo (cache + Docker)"
	@echo ""
	@echo "$(GREEN)Análisis específicos:$(NC)"
	@echo "  $(YELLOW)make apps$(NC)         - Analizar /Applications"
	@echo "  $(YELLOW)make downloads$(NC)    - Analizar ~/Downloads"
	@echo "  $(YELLOW)make dev$(NC)          - Analizar ~/Developer"
	@echo "  $(YELLOW)make documents$(NC)    - Analizar ~/Documents"
	@echo ""
	@echo "$(GREEN)Utilidades:$(NC)"
	@echo "  $(YELLOW)make install$(NC)      - Instalar dependencias"
	@echo "  $(YELLOW)make check$(NC)        - Verificar que todo esté instalado"
	@echo "  $(YELLOW)make open$(NC)         - Abrir el último reporte HTML"
	@echo ""
	@echo "$(GREEN)Interfaz Gráfica:$(NC)"
	@echo "  $(YELLOW)make gui$(NC)          - Ejecutar interfaz gráfica moderna"
	@echo "  $(YELLOW)make install-gui$(NC)  - Instalar dependencias para GUI"
	@echo "  $(YELLOW)make web$(NC)          - Ejecutar interfaz web (sin problemas de GUI!)"
	@echo "  $(YELLOW)make install-web$(NC)  - Instalar dependencias para web"
	@echo ""
	@echo "$(BLUE)Ejemplos:$(NC)"
	@echo "  make analyze path=/Users/me/Projects"
	@echo "  make quick min_size=100"
	@echo "  make full path=/ min_size=500"
	@echo "$(BLUE)═══════════════════════════════════════════════════════════════$(NC)"

# Análisis estándar
analyze:
	@echo "$(GREEN)🔍 Iniciando análisis de disco...$(NC)"
	@$(PYTHON) $(SCRIPT) $(DEFAULT_PATH) --min-size $(MIN_SIZE)

# Análisis rápido (solo archivos grandes)
quick:
	@echo "$(GREEN)⚡ Análisis rápido (archivos > 50MB)...$(NC)"
	@$(PYTHON) $(SCRIPT) $(DEFAULT_PATH) --min-size 50

# Análisis completo con exportación
full:
	@echo "$(GREEN)📊 Análisis completo con reporte HTML...$(NC)"
	@$(PYTHON) $(SCRIPT) $(or $(path),$(DEFAULT_PATH)) --min-size $(or $(min_size),$(MIN_SIZE)) --export $(REPORT_NAME) --html
	@echo "$(GREEN)✅ Reporte generado: $(REPORT_NAME).html$(NC)"
	@echo "$(YELLOW)   Abriendo en el navegador...$(NC)"
	@open $(REPORT_NAME).html

# Generar solo reporte HTML
report:
	@echo "$(GREEN)📄 Generando reporte HTML...$(NC)"
	@$(PYTHON) $(SCRIPT) $(or $(path),$(DEFAULT_PATH)) --min-size $(or $(min_size),$(MIN_SIZE)) --export $(REPORT_NAME) --html
	@open $(REPORT_NAME).html

# Vista previa de limpieza
clean-preview:
	@echo "$(YELLOW)👀 Vista previa de limpieza (no se borrará nada)...$(NC)"
	@$(PYTHON) $(SCRIPT) $(DEFAULT_PATH) --clean-all --dry-run

# Limpiar cache
clean-cache:
	@echo "$(RED)🧹 Limpiando cache del sistema...$(NC)"
	@$(PYTHON) $(SCRIPT) $(DEFAULT_PATH) --clean-cache

# Limpiar Docker
clean-docker:
	@echo "$(RED)🐳 Limpiando recursos Docker...$(NC)"
	@$(PYTHON) $(SCRIPT) $(DEFAULT_PATH) --clean-docker

# Limpiar todo
clean-all:
	@echo "$(RED)🔥 Limpiando cache y Docker...$(NC)"
	@$(PYTHON) $(SCRIPT) $(DEFAULT_PATH) --clean-all

# Análisis de directorios específicos
apps:
	@echo "$(GREEN)📱 Analizando aplicaciones...$(NC)"
	@$(PYTHON) $(SCRIPT) /Applications --min-size 50

downloads:
	@echo "$(GREEN)📥 Analizando descargas...$(NC)"
	@$(PYTHON) $(SCRIPT) ~/Downloads --min-size 10

dev:
	@echo "$(GREEN)💻 Analizando directorio de desarrollo...$(NC)"
	@$(PYTHON) $(SCRIPT) ~/Developer --min-size 50

documents:
	@echo "$(GREEN)📄 Analizando documentos...$(NC)"
	@$(PYTHON) $(SCRIPT) ~/Documents --min-size 20

# Análisis personalizado
custom:
	@if [ -z "$(path)" ]; then \
		echo "$(RED)Error: Especifica una ruta. Ejemplo: make custom path=/ruta/a/analizar$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)🔍 Analizando $(path)...$(NC)"
	@$(PYTHON) $(SCRIPT) $(path) --min-size $(or $(min_size),$(MIN_SIZE))

# Verificar instalación
check:
	@echo "$(BLUE)🔍 Verificando dependencias...$(NC)"
	@echo -n "Python 3: "
	@if command -v python3 >/dev/null 2>&1; then \
		echo "$(GREEN)✓ $(shell python3 --version)$(NC)"; \
	else \
		echo "$(RED)✗ No instalado$(NC)"; \
	fi
	@echo -n "tkinter (GUI): "
	@if $(PYTHON) -c "import tkinter" 2>/dev/null; then \
		echo "$(GREEN)✓ Instalado$(NC)"; \
	else \
		echo "$(RED)✗ No instalado (requerido para GUI)$(NC)"; \
	fi
	@echo -n "CustomTkinter: "
	@if $(PYTHON) -c "import customtkinter" 2>/dev/null; then \
		echo "$(GREEN)✓ Instalado$(NC)"; \
	else \
		echo "$(YELLOW)⚠ No instalado (ejecuta 'make install')$(NC)"; \
	fi
	@echo -n "Docker: "
	@if command -v docker >/dev/null 2>&1; then \
		echo "$(GREEN)✓ $(shell docker --version | cut -d' ' -f3 | tr -d ',')$(NC)"; \
	else \
		echo "$(YELLOW)⚠ No instalado (opcional)$(NC)"; \
	fi

# Instalar dependencias (si es necesario)
install:
	@echo "$(GREEN)📦 Verificando Python...$(NC)"
	@if ! command -v python3 >/dev/null 2>&1; then \
		echo "$(RED)Python 3 no está instalado. Instálalo con: brew install python3$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)Verificando tkinter (interfaz gráfica base)...$(NC)"
	@if ! $(PYTHON) -c "import tkinter" 2>/dev/null; then \
		echo "$(RED)⚠️  tkinter no está instalado$(NC)"; \
		echo "$(YELLOW)tkinter es necesario para la interfaz gráfica.$(NC)"; \
		echo ""; \
		if [ "$$(uname)" = "Linux" ]; then \
			if [ -f /etc/debian_version ]; then \
				echo "$(YELLOW)Ejecuta: sudo apt install python3-tk$(NC)"; \
			elif [ -f /etc/fedora-release ]; then \
				echo "$(YELLOW)Ejecuta: sudo dnf install python3-tkinter$(NC)"; \
			elif [ -f /etc/arch-release ]; then \
				echo "$(YELLOW)Ejecuta: sudo pacman -S tk$(NC)"; \
			elif [ -f /etc/SuSE-release ] || [ -f /etc/SUSE-brand ]; then \
				echo "$(YELLOW)Ejecuta: sudo zypper install python3-tk$(NC)"; \
			else \
				echo "$(YELLOW)Instala python3-tk o python3-tkinter según tu distribución$(NC)"; \
			fi; \
		elif [ "$$(uname)" = "Darwin" ]; then \
			echo "$(YELLOW)Ejecuta: brew install python-tk$(NC)"; \
		fi; \
		echo ""; \
		echo "$(YELLOW)Después de instalar tkinter, ejecuta 'make install' nuevamente$(NC)"; \
		echo ""; \
	else \
		echo "$(GREEN)✅ tkinter está instalado$(NC)"; \
	fi
	@echo "$(GREEN)📦 Instalando dependencias para GUI...$(NC)"
	@$(PYTHON) -m pip install -r requirements.txt 2>/dev/null || pip install -r requirements.txt
	@echo "$(GREEN)✅ Todo listo para usar (CLI y GUI)$(NC)"

# Abrir último reporte
open:
	@LATEST=$$(ls -t disk_report_*.html 2>/dev/null | head -1); \
	if [ -z "$$LATEST" ]; then \
		echo "$(RED)No se encontraron reportes HTML$(NC)"; \
	else \
		echo "$(GREEN)Abriendo $$LATEST...$(NC)"; \
		open "$$LATEST"; \
	fi

# Limpiar reportes antiguos
clean-reports:
	@echo "$(YELLOW)🗑️  Limpiando reportes antiguos (manteniendo los últimos 5)...$(NC)"
	@ls -t disk_report_*.html 2>/dev/null | tail -n +6 | xargs -I {} rm -f {}
	@ls -t disk_report_*.json 2>/dev/null | tail -n +6 | xargs -I {} rm -f {}
	@echo "$(GREEN)✅ Reportes antiguos eliminados$(NC)"

# Estadísticas del sistema
stats:
	@echo "$(BLUE)📊 Estadísticas del Sistema$(NC)"
	@echo "$(BLUE)═══════════════════════════════════════════$(NC)"
	@echo "$(GREEN)Espacio en disco:$(NC)"
	@df -h | grep -E "^/|Filesystem"
	@echo ""
	@echo "$(GREEN)Top 5 directorios en HOME:$(NC)"
	@du -sh ~/* 2>/dev/null | sort -hr | head -5
	@if command -v docker >/dev/null 2>&1; then \
		echo ""; \
		echo "$(GREEN)Docker:$(NC)"; \
		docker system df 2>/dev/null || echo "$(YELLOW)Docker no está ejecutándose$(NC)"; \
	fi

# GUI Commands
install-gui:
	@echo "$(GREEN)📦 Instalando dependencias para la interfaz gráfica...$(NC)"
	@echo "$(BLUE)Usando Python: $(PYTHON)$(NC)"
	@$(PYTHON) -m pip install -r requirements.txt || echo "$(RED)Error al instalar con $(PYTHON)$(NC)"
	@echo "$(GREEN)✅ Dependencias GUI instaladas$(NC)"
	@echo "$(BLUE)Verificando instalación...$(NC)"
	@$(PYTHON) -c "import customtkinter; print('✅ CustomTkinter instalado correctamente')" || echo "$(RED)❌ CustomTkinter NO se instaló correctamente$(NC)"

gui:
	@echo "$(GREEN)🎨 Iniciando interfaz gráfica...$(NC)"
	@echo "$(BLUE)Verificando CustomTkinter con $(PYTHON)...$(NC)"
	@if ! $(PYTHON) -c "import customtkinter" 2>&1; then \
		echo "$(RED)Error: CustomTkinter no está instalado$(NC)"; \
		echo "$(YELLOW)Intenta ejecutar: $(PYTHON) -m pip install customtkinter$(NC)"; \
		echo "$(YELLOW)O verifica tu instalación con: make check-gui$(NC)"; \
		exit 1; \
	fi
	@$(PYTHON) disk_analyzer_gui.py

# Verificar instalación de GUI
check-gui:
	@echo "$(BLUE)🔍 Diagnóstico de instalación GUI$(NC)"
	@echo "$(BLUE)═══════════════════════════════════$(NC)"
	@echo "Python ejecutable: $(PYTHON)"
	@$(PYTHON) --version
	@echo ""
	@echo "Ubicación de Python:"
	@which $(PYTHON)
	@echo ""
	@echo "Ubicación de pip:"
	@which pip3 || which pip || echo "pip no encontrado"
	@echo ""
	@echo "Verificando paquetes GUI:"
	@$(PYTHON) -m pip list | grep -E "customtkinter|matplotlib|Pillow" || echo "Paquetes no encontrados"
	@echo ""
	@echo "Intentando importar customtkinter:"
	@$(PYTHON) -c "import customtkinter; print('✅ CustomTkinter versión:', customtkinter.__version__)" 2>&1 || echo "$(RED)❌ Error al importar$(NC)"
	@echo ""
	@echo "Path de Python:"
	@$(PYTHON) -c "import sys; print('\n'.join(sys.path[:5]))"

# Web Interface Commands
install-web:
	@echo "$(GREEN)🌐 Instalando dependencias para interfaz web...$(NC)"
	@$(PYTHON) -m pip install -r requirements-web.txt || pip install -r requirements-web.txt
	@echo "$(GREEN)✅ Servidor web listo para usar$(NC)"

web:
	@echo "$(GREEN)🌐 Iniciando servidor web...$(NC)"
	@echo "$(BLUE)Verificando dependencias...$(NC)"
	@$(PYTHON) -c "import fastapi" 2>/dev/null || (echo "$(YELLOW)Instalando dependencias web...$(NC)" && $(PYTHON) -m pip install -r requirements-web.txt)
	@echo "$(GREEN)✅ Servidor iniciando en http://localhost:8000$(NC)"
	@echo "$(BLUE)📚 API Docs en http://localhost:8000/docs$(NC)"
	@echo ""
	@$(PYTHON) disk_analyzer_web.py

# Comando por defecto
.DEFAULT_GOAL := help