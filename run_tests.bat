@echo off
REM Script para ejecutar tests automatizados en Windows
REM Herramienta de Gestión Remota para Windows

echo ================================================
echo    Tests Automatizados - Sistema de Gestion
echo ================================================
echo.

REM Verificar que Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no esta instalado o no esta en el PATH
    pause
    exit /b 1
)

REM Verificar que pytest está instalado
python -m pytest --version >nul 2>&1
if errorlevel 1 (
    echo Instalando dependencias de testing...
    pip install -r requirements-dev.txt
    if errorlevel 1 (
        echo ERROR: No se pudieron instalar las dependencias
        pause
        exit /b 1
    )
)

echo Dependencias verificadas correctamente
echo.

REM Menú de opciones
:MENU
echo Seleccione el tipo de test a ejecutar:
echo.
echo 1. Todos los tests (completo)
echo 2. Solo tests unitarios
echo 3. Solo tests de integracion
echo 4. Tests con coverage detallado
echo 5. Tests rapidos (sin coverage)
echo 6. Tests de un modulo especifico
echo 7. Generar reporte HTML de coverage
echo 8. Limpiar archivos de test
echo 9. Salir
echo.

set /p option="Ingrese su opcion (1-9): "

if "%option%"=="1" goto ALL_TESTS
if "%option%"=="2" goto UNIT_TESTS
if "%option%"=="3" goto INTEGRATION_TESTS
if "%option%"=="4" goto COVERAGE_TESTS
if "%option%"=="5" goto FAST_TESTS
if "%option%"=="6" goto SPECIFIC_TESTS
if "%option%"=="7" goto HTML_REPORT
if "%option%"=="8" goto CLEAN
if "%option%"=="9" goto END

echo Opcion invalida
goto MENU

:ALL_TESTS
echo.
echo Ejecutando TODOS los tests...
echo.
python -m pytest tests/ -v
goto RESULTS

:UNIT_TESTS
echo.
echo Ejecutando tests UNITARIOS...
echo.
python -m pytest tests/unit/ -v -m unit
goto RESULTS

:INTEGRATION_TESTS
echo.
echo Ejecutando tests de INTEGRACION...
echo.
python -m pytest tests/integration/ -v -m integration
goto RESULTS

:COVERAGE_TESTS
echo.
echo Ejecutando tests con COVERAGE detallado...
echo.
python -m pytest tests/ -v --cov=modules --cov=utils --cov=main --cov-report=term-missing --cov-report=html
echo.
echo Reporte HTML generado en: htmlcov/index.html
goto RESULTS

:FAST_TESTS
echo.
echo Ejecutando tests RAPIDOS (sin coverage)...
echo.
python -m pytest tests/ -v --no-cov -x
goto RESULTS

:SPECIFIC_TESTS
echo.
echo Modulos disponibles:
echo   - parsers
echo   - cache
echo   - api
echo   - backup
echo   - partitions
echo.
set /p module="Ingrese el nombre del modulo: "
echo.
echo Ejecutando tests de %module%...
echo.
python -m pytest tests/ -v -k %module%
goto RESULTS

:HTML_REPORT
echo.
echo Generando reporte HTML...
echo.
python -m pytest tests/ --cov=modules --cov=utils --cov=main --cov-report=html
if errorlevel 1 (
    echo ERROR: No se pudo generar el reporte
) else (
    echo Reporte generado exitosamente en: htmlcov/index.html
    echo Abriendo reporte en el navegador...
    start htmlcov/index.html
)
goto RESULTS

:CLEAN
echo.
echo Limpiando archivos de test...
if exist htmlcov rmdir /s /q htmlcov
if exist .pytest_cache rmdir /s /q .pytest_cache
if exist .coverage del /f /q .coverage
if exist coverage.xml del /f /q coverage.xml
echo Archivos limpiados correctamente
echo.
pause
goto MENU

:RESULTS
echo.
echo ================================================
if errorlevel 1 (
    echo    RESULTADO: ALGUNOS TESTS FALLARON
    echo ================================================
    echo.
    echo Revise el output anterior para ver los detalles
) else (
    echo    RESULTADO: TODOS LOS TESTS PASARON
    echo ================================================
)
echo.

:ASK_CONTINUE
set /p continue="Desea ejecutar mas tests? (s/n): "
if /i "%continue%"=="s" goto MENU
if /i "%continue%"=="n" goto END
echo Opcion invalida
goto ASK_CONTINUE

:END
echo.
echo Finalizando tests...
echo.
pause
