# Third-party notices

The Python dependencies are installed according to `pyproject.toml` and retain their respective licences.

The current Windows bundle uses the FFmpeg executable from `imageio-ffmpeg` 0.6.0. The bundled binary reports FFmpeg 7.1, `essentials_build-www.gyan.dev`, configured with `--enable-gpl --enable-version3`, and GNU GPL version 3 or later. Its full licence and configuration are available by running the bundled executable with `-L` and `-buildconf`. See <https://ffmpeg.org/legal.html> and <https://www.gyan.dev/ffmpeg/builds/> for the binary provider and corresponding build sources. If a different binary is bundled later, update this notice to match it.

ACE-Step model weights, source code, and services are not bundled with the professor distribution or `.remix` projects. Creator setup obtains the official ACE-Step 1.5 project from <https://github.com/ACE-Step/ACE-Step-1.5> and selects tested Git revision `ca1e85fe9430179831e6bc6be790c332190a3866`. The upstream project identifies its code as MIT-licensed; downloaded model files remain subject to the licence and notices supplied by that upstream project. Remixii communicates only with its local API at `http://127.0.0.1:8001`.
