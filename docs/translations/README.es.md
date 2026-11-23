<div align="center">

# Bitwarden Duplicate Merger

**Encuentra y fusiona los inicios de sesión duplicados de tu caja fuerte de Bitwarden, con una pantalla de revisión antes de cualquier cambio.**

[![tests](https://github.com/ThomLaurent/bitwarden-duplicate-merger/actions/workflows/tests.yml/badge.svg)](https://github.com/ThomLaurent/bitwarden-duplicate-merger/actions/workflows/tests.yml)
[![release](https://img.shields.io/github/v/release/ThomLaurent/bitwarden-duplicate-merger?label=download)](https://github.com/ThomLaurent/bitwarden-duplicate-merger/releases/latest)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)
[![license](https://img.shields.io/badge/license-Unlicense-blue)](../../LICENSE)

[English](../../README.md) · [Français](README.fr.md) · Español · [Deutsch](README.de.md) · [简体中文](README.zh-CN.md)

<img src="../screenshots/review-conflict.png" alt="Pantalla de revisión: tres inicios de sesión de Steam con dos contraseñas distintas" width="900">

</div>

Tras importar contraseñas desde un navegador u otro gestor, una caja fuerte suele contener la misma cuenta varias veces: `www.amazon.es`, `login.amazon.es` y `amazon.es/ap/signin`, con el mismo usuario y la misma contraseña. Bitwarden no permite fusionarlos, y hacerlo a mano con cientos de entradas lleva horas.

Esta herramienta agrupa esos duplicados, propone una fusión para cada grupo, te deja revisar y cambiar cada decisión en una página web local y luego aplica solo lo que has validado, mediante la CLI oficial de Bitwarden.

## Cómo funciona

1. **Inicia la herramienta.** La CLI de Bitwarden desbloquea la caja fuerte y se abre una página en tu navegador.
2. **Revisa las sugerencias.** Los inicios de sesión con el mismo dominio y usuario se agrupan. Los grupos que la regla no puede resolver sola (contraseñas distintas, passkeys...) se marcan para ti.
3. **Cambia lo que quieras**: elemento conservado, nombre, contraseña, TOTP, notas, URIs, elementos que dejar fuera. Agrupa entradas a mano si hace falta (`ebay.es` y `ebay.com`).
4. **Para y continúa cuando quieras.** Las decisiones se guardan en un archivo, incluso tras reiniciar.
5. **Aplica** todos los grupos validados o solo algunos. Un informe muestra lo realizado, empezando por lo que decidiste distinto de la regla.

## Garantías

- **Tu contraseña maestra nunca llega a la herramienta.** Solo la lee la CLI de Bitwarden; la herramienta recibe la clave de sesión y la guarda en memoria.
- **Ningún secreto se escribe en disco ni en registros.** Contraseñas, claves TOTP, campos y notas se comparan en memoria. La página muestra uno solo si pulsas "show".
- **Nada cambia sin tu validación**, y solo se aplican los grupos validados.
- **Ningún plan obsoleto.** Justo antes de cada grupo, la herramienta comprueba con Bitwarden que ningún elemento cambió desde tu revisión. Si cambió, el grupo se omite y se indica.
- **Reversible.** Los duplicados van a la papelera de Bitwarden (30 días), los elementos conservados mantienen su ID, adjuntos y passkeys, y se hace una copia cifrada antes de aplicar.
- **Solo local.** La página se sirve en `127.0.0.1` con un token aleatorio. Sin acceso a la red salvo `bw` hacia tu servidor de Bitwarden, y la descarga de `bw` descrita abajo.
- **CLI oficial de Bitwarden.** Si `bw` no está instalado, la herramienta ofrece descargarlo desde las versiones de Bitwarden en GitHub y comprueba su SHA-256. Mantiene esa copia actualizada, comprobándolo una vez al mes.
- **Pequeña y legible.** Unas 2.300 líneas de Python y JavaScript, solo biblioteca estándar, sin dependencias que auditar.

## Inicio rápido

<details open>
<summary><b>Windows</b></summary>

1. Descarga **`bw-dedupe-windows-x64.exe`** desde la [última versión](https://github.com/ThomLaurent/bitwarden-duplicate-merger/releases/latest).
2. Muévelo a una carpeta propia, por ejemplo una nueva carpeta `bw-dedupe` en Documentos. Tus decisiones e informes se guardan a su lado.
3. Haz doble clic en él. Si Windows muestra «Windows protegió su PC», haz clic en **Más información** y luego en **Ejecutar de todas formas**: el archivo no está firmado.
4. Se abre una ventana negra. La primera vez, ofrece descargar la herramienta oficial de línea de comandos de Bitwarden: pulsa Intro. Para echar antes un vistazo con una caja fuerte ficticia, escribe `D` y pulsa Intro.
5. Elige dónde está tu cuenta (bitwarden.com, bitwarden.eu o tu propio servidor) e inicia sesión: correo, contraseña maestra y código de inicio de sesión en dos pasos si lo usas. No se ve nada mientras escribes la contraseña, es normal.
6. La página de revisión se abre en tu navegador.

</details>

<details>
<summary><b>macOS</b></summary>

1. Descarga **`bw-dedupe-macos-arm64.zip`** desde la [última versión](https://github.com/ThomLaurent/bitwarden-duplicate-merger/releases/latest). Funciona en Mac con chip de Apple (M1 o posterior); en un Mac con Intel, ejecútalo desde el código fuente.
2. Abre el zip si Safari no lo hizo ya y mueve `bw-dedupe-macos-arm64` a una carpeta propia, por ejemplo una nueva carpeta `bw-dedupe` en Documentos. Tus decisiones e informes se guardan a su lado.
3. Haz doble clic en él. La primera vez, macOS lo rechaza porque el archivo no está firmado: haz clic en **OK**, abre **Ajustes del Sistema**, luego **Privacidad y seguridad**, baja y haz clic en **Abrir igualmente**, y confirma.
4. Se abre una ventana de Terminal. La primera vez, ofrece descargar la herramienta oficial de línea de comandos de Bitwarden: pulsa Intro. Para echar antes un vistazo con una caja fuerte ficticia, escribe `D` y pulsa Intro.
5. Elige dónde está tu cuenta (bitwarden.com, bitwarden.eu o tu propio servidor) e inicia sesión: correo, contraseña maestra y código de inicio de sesión en dos pasos si lo usas. No se ve nada mientras escribes la contraseña, es normal.
6. La página de revisión se abre en tu navegador.

</details>

<details>
<summary><b>Linux</b></summary>

Descarga **`bw-dedupe-linux-x64`** desde la [última versión](https://github.com/ThomLaurent/bitwarden-duplicate-merger/releases/latest) y luego, en una terminal:

```bash
chmod +x bw-dedupe-linux-x64
```
```bash
./bw-dedupe-linux-x64
```

La primera vez, la herramienta ofrece descargar la CLI oficial de Bitwarden, o probar una caja fuerte de demostración. Inicia sesión cuando `bw` lo pida y revisa en la página que se abre.

</details>

<details>
<summary><b>Desde el código fuente</b> (cualquier sistema con Python 3.10+)</summary>

Sin instalar nada:

```bash
git clone https://github.com/ThomLaurent/bitwarden-duplicate-merger
```
```bash
cd bitwarden-duplicate-merger
```
```bash
python bw_dedupe.py
```

</details>

**Pruébala antes** con una caja fuerte ficticia, sin CLI de Bitwarden ni cuenta: escribe `D` cuando la herramienta ofrezca descargar la CLI, o iníciala desde una terminal con `--demo` (por ejemplo `python bw_dedupe.py --demo`). No se guarda nada en ninguna caja fuerte.

Los ejecutables incluyen su propio Python: siguen funcionando con cualquier versión de Python que tengas, mientras `bw` mantenga sus comandos. Cada uno se compila con GitHub Actions desde este repositorio y se verifica con:

```bash
gh attestation verify bw-dedupe-windows-x64.exe --repo ThomLaurent/bitwarden-duplicate-merger
```

Más detalles (en inglés): [guía de uso](../USAGE.md).

## Estado del proyecto

Esta herramienta se comparte **tal cual** y probablemente no se mejorará. La hice para limpiar mi propia caja fuerte y preferí compartirla abiertamente en lugar de guardarla para mí. Espero que te ahorre el tiempo y los tokens de crear lo mismo y, sobre todo, las horas de fusionar cientos de entradas a mano.

Puede que las issues y pull requests no reciban respuesta. Los forks son bienvenidos: el código es de dominio público ([Unlicense](../../LICENSE)), y [AGENTS.md](../../AGENTS.md) lo explica a ti y a los asistentes de programación con IA.

Sin relación con Bitwarden, Inc. "Bitwarden" es una marca de Bitwarden, Inc.
