# PlayStation Accessories - Open Source Edition 🎮

Un clone **open-source**, leggero, moderno e privo di telemetria dell'applicazione ufficiale **Sony PlayStation Accessories**, progettato per gestire sia il controller **DualSense** standard che il controller avanzato **DualSense Edge**.

**Versione 3.0 — ora multipiattaforma: Windows, macOS e Linux.**

---

## 🆕 Novità della versione 3.0

- **Supporto macOS nativo**: nuovo backend HID basato su **IOKit / IOHIDManager**, chiamato via `ctypes` come quello Windows. Nessun driver aggiuntivo, nessuna libreria esterna.
- **Supporto Linux**: backend `hidraw`, così l'app funziona anche sulle distro desktop.
- **Selezione automatica del backend**: un unico punto di ingresso (`app/controller/hid_base.py`) sceglie il backend giusto in base al sistema operativo; su sistemi non supportati l'interfaccia si avvia comunque, senza crash.
- **Launcher dedicati**: `run.command` (doppio click su macOS), `run.sh` (macOS/Linux), `run.bat` (Windows).
- **Robustezza**: salvataggio profili atomico con fallback nella cartella utente, gestione porte occupate, spegnimento pulito con `CTRL+C`, niente traceback se il browser chiude la connessione.
- **Diagnostica nella UI**: sistema operativo, backend HID attivo, versione e stato del flusso dati in tempo reale.
- **Suite di test automatica** (33 test, nessun hardware richiesto).

---

## 🌟 Caratteristiche Principali

- **100% Hardware Reale Diretto**: zero modalità demo o simulazioni fittizie. Comunica direttamente con l'hardware fisico del tuo DualSense (`PID 0x0CE6`) o DualSense Edge (`PID 0x0DF2`) collegato sia via **cavo USB** che via **Bluetooth**.
- **Rilevamento a Caldo (Hot-Plug)**: monitora costantemente la connessione; se colleghi o scolleghi il controller o passi da cavo a Bluetooth, viene rilevato all'istante.
- **Zero Dipendenze Esterne**: funziona con l'interprete Python 3 standard (3.8 o superiore). Nessun pacchetto `pip`, nessuna wheel: parla con le API native del sistema operativo (`SetupAPI.dll`/`HID.dll` su Windows, `IOKit.framework`/`CoreFoundation.framework` su macOS, `hidraw` su Linux) tramite solo `ctypes` e la libreria standard.
- **Nessuna Telemetria o Tracking**: a differenza dell'app proprietaria ufficiale, questo clone è locale al 100%.
- **Tester Interattivo Live in Tempo Reale**:
  - Visualizzazione grafica e reattiva di tutti i pulsanti (✕, ◯, ▢, △, D-Pad, L1, R1, L2, R2, L3, R3, Create, Options, PS, Touchpad, Fn e Paddle posteriori).
  - Radar a cerchio con reticolo delle levette analogiche (coordinate esatte, deviazione e cerchio della deadzone interna).
  - Indicatori di pressione progressiva dei grilletti L2 ed R2 (0-255).
  - Test rapido dei motori del feedback aptico / vibrazione.
  - Indicatore di stato batteria e carica.
- **Gestore Profili Avanzato DualSense Edge**:
  - **Curve di Sensibilità Ufficiali con rendering matematico in tempo reale**: *Lineare*, *Rapido (Quick)*, *Preciso (Precise)*, *Costante (Steady)*, *Digitale (Digital)*, *Dinamico (Dynamic S-Curve)*.
  - Regolazione fine delle zone morte (*deadzone*) e anti-deadzone.
  - Regolazione della soglia dei grilletti (*Hair-Trigger*).
  - Rimappatura completa dei tasti posteriori (*Back Paddles LB / RB*).
- **Assegnazione Slot Profilo (Scorciatoie Fn)**: Slot 1 (`Fn + △`), Slot 2 (`Fn + ◯`), Slot 3 (`Fn + ✕`), Slot 4 (`Fn + ▢`).
- **Controllo Barra Luminosa (RGB Lightbar) & Player LED**: color picker, preset rapidi e invio dei comandi di output HID reali.

---

## 🚀 Avvio rapido

Requisito unico: **Python 3.8 o superiore** ([python.org](https://www.python.org/downloads/)). Nessuna dipendenza da installare.

### 🍎 macOS (novità V3.0)

1. **Apri il Terminale** (Spotlight → “Terminale”) e verifica Python:
   ```bash
   python3 --version
   ```
   Se manca, installalo da [python.org](https://www.python.org/downloads/) oppure con `brew install python`.

2. **Entra nella cartella del progetto e avvia**:
   ```bash
   cd ~/Desktop/Programmi/PlayStationAccessories
   ./run.command
   ```
   In alternativa, dal Finder: **doppio click su `run.command`**.
   Se macOS blocca il file appena scaricato, esegui una volta:
   ```bash
   chmod +x run.sh run.command
   xattr -dr com.apple.quarantine .
   ```

3. **Concedi il permesso “Monitoraggio input”** (obbligatorio da macOS 10.15):
   *Impostazioni di Sistema → Privacy e Sicurezza → Monitoraggio input* → abilita **Terminale** (o iTerm/VS Code, cioè il programma da cui lanci l'app) → **chiudi e riapri il Terminale**.
   Senza questo permesso il controller viene elencato ma i dati non arrivano: la UI mostra “In attesa di report...”.

4. **Collega il controller**:
   - **USB**: basta il cavo, il DualSense viene rilevato subito.
   - **Bluetooth**: tieni premuti **PS + Create** finché la lightbar non lampeggia due volte, poi accoppialo da *Impostazioni di Sistema → Bluetooth* (appare come “Wireless Controller” / “DualSense Wireless Controller”).

5. Il browser si apre da solo su **http://127.0.0.1:8080**. Per chiudere l'app: `CTRL+C` nel Terminale.

> **Nota macOS**: l'app apre il controller in modalità *condivisa*, quindi il pad continua a funzionare nei giochi. Se il driver di sistema lo occupa in esclusiva, viene effettuato un secondo tentativo in modalità esclusiva (l'app lo segnala a terminale): in quel caso il controller torna disponibile ai giochi appena chiudi l'applicazione.

### 🪟 Windows

Metodo 1 — doppio click su **`run.bat`** (o sul collegamento sul Desktop).
Metodo 2 — da PowerShell / Prompt:
```powershell
cd "C:\Users\Valerio\Desktop\Programmi\PlayStationAccessories"
python app\main.py
```
`run.bat` usa automaticamente `py -3` se il launcher Python è installato, altrimenti `python`.

### 🐧 Linux

```bash
cd open-playstation-accessories
./run.sh
```
Serve accesso ai nodi `/dev/hidraw*`: aggiungi il tuo utente al gruppo `input` oppure installa una regola udev, ad esempio:
```bash
sudo usermod -aG input "$USER"      # poi effettua logout/login
```

### Opzioni della riga di comando

```bash
python3 app/main.py --help
python3 app/main.py --port 8090 --no-browser
python3 app/main.py --host 0.0.0.0          # accessibile dalla rete locale
python3 app/main.py --profiles /percorso/miei-profili.json
```

| Opzione | Descrizione |
| --- | --- |
| `--host` | Indirizzo di ascolto (default `127.0.0.1`) |
| `--port` | Porta HTTP (default `8080`, se occupata viene scelta la successiva libera) |
| `--no-browser` | Non aprire il browser automaticamente |
| `--profiles` | Percorso alternativo per `profiles.json` |
| `--version` | Stampa la versione |

---

## 🧠 Come funziona su macOS

Su macOS non esiste `SetupAPI`: i controller HID vengono gestiti da **IOKit**. Il backend `app/controller/hid_macos.py`:

1. crea un `IOHIDManager` e enumera le periferiche HID del sistema, filtrando per vendor Sony `0x054C` e per i Product ID supportati;
2. apre l'interfaccia “gamepad” con `IOHIDDeviceOpen` (condivisa, senza sequestrare la periferica);
3. registra una callback di **input report** su un thread dedicato con un `CFRunLoop`; macOS consegna il payload senza report ID, che viene ri-anteposto per mantenere **identico** il formato usato su Windows (quindi lo stesso parser `dualsense.py`);
4. invia i comandi di uscita (lightbar, vibrazione, LED) con `IOHIDDeviceSetReport`, passando il report ID separatamente come previsto dall'API Apple.

Tutto avviene tramite `ctypes`: nessun binding da compilare, nessun `pip install`, e il codice resta leggibile come quello Windows.

---

## 📐 Architettura del Progetto

```
PlayStationAccessories/
├── app/
│   ├── controller/
│   │   ├── hid_base.py       # Selettore di backend (win32 / darwin / linux) + Null backend
│   │   ├── hid_windows.py    # Backend Windows nativo (SetupAPI.dll / HID.dll via ctypes)
│   │   ├── hid_macos.py      # Backend macOS nativo (IOKit.IOHIDManager via ctypes)  [V3.0]
│   │   ├── hid_linux.py      # Backend Linux (/dev/hidraw*)                          [V3.0]
│   │   └── dualsense.py      # Parser pacchetti HID DualSense (0x01/0x31) & output report (0x02/0x31)
│   ├── profiles/
│   │   └── manager.py        # Gestione profili JSON (salvataggio atomico), curve e slot Fn
│   ├── web/
│   │   ├── server.py         # Server HTTP REST (ThreadingHTTPServer) + API /api/*
│   │   ├── preview_server.py # Launcher di sviluppo (0.0.0.0)
│   │   └── static/           # index.html, style.css, app.js (PS5 Fluent Dark)
│   └── main.py               # Supervisore hot-plug, argomenti CLI e lifecycle
├── tests/
│   ├── test_smoke.py         # 28 test (backend, parser, report, API HTTP, profili, hot-plug)
│   └── test_macos_backend.py # 5 test IOKit simulato (enumerazione, callback, output)
├── profiles.json             # Archivio profili e configurazioni salvate
├── run.command               # Launcher macOS (doppio click)
├── run.sh                    # Launcher macOS / Linux
├── run.bat                   # Launcher Windows
└── README.md
```

### API REST locale

| Metodo | Endpoint | Descrizione |
| --- | --- | --- |
| GET | `/api/status` | Connessione, modello, batteria, lightbar, piattaforma/backend |
| GET | `/api/inputs` | Levette, grilletti e pulsanti in tempo reale |
| GET | `/api/platform` | Sistema operativo e backend HID attivo |
| GET | `/api/profiles` | Profili salvati, slot e slot attivo |
| GET | `/api/health` | Health-check |
| POST | `/api/lightbar` | `{"r":0,"g":112,"b":240}` |
| POST | `/api/rumble` | `{"left":128,"right":128,"duration":0.5}` |
| POST | `/api/player_led` | `{"player_num":1}` |
| POST | `/api/profiles/save` \| `/delete` | Salva / elimina profilo |
| POST | `/api/slots/assign` \| `/select` | Assegna / attiva slot |

---

## 🧪 Test

La suite non richiede controller collegati e gira su tutti i sistemi:

```bash
python3 -m unittest discover -s tests -t .
```

Copre: selezione backend, import sicuri dei backend macOS/Linux, parsing report USB/Bluetooth (incluse levette, grilletti, batteria, pulsanti Edge), costruzione dei report di output con CRC Bluetooth, API HTTP, salvataggio profili, ciclo hot-plug e logica del backend IOKit simulato (enumerazione, filtro per vendor/product, callback degli input report, scrittura degli output).

---

## 🛠️ Risoluzione problemi

| Sintomo | Causa / Soluzione |
| --- | --- |
| Su macOS il controller è elencato ma i valori restano a zero | Manca il permesso **Monitoraggio input** per il Terminale: abilitalo e **riavvia** il Terminale. |
| `permission denied` eseguendo `./run.command` | `chmod +x run.sh run.command` |
| `zsh: bad CPU type in executable` | Python installato per un'altra architettura (Intel vs Apple Silicon): reinstalla Python da python.org. |
| La porta 8080 è occupata | L'app passa automaticamente alla successiva; oppure usa `--port 8090`. |
| Il controller non appare su Bluetooth (macOS) | Rimuovi l'accoppiamento precedente, tieni premuti **PS + Create** fino al doppio lampeggio e ri-associa. |
| La lightbar non cambia colore | Alcuni firmware gestiscono il LED a livello di sistema; verifica che il controller non sia in carica da un hub senza alimentazione. |
| File `profiles.json` non scrivibile | L'app salva automaticamente in `~/Library/Application Support/PlayStationAccessories` (macOS), `%APPDATA%\PlayStationAccessories` (Windows) o `~/.config/playstation-accessories` (Linux). |

---

## ⚖️ Licenza

Distribuito sotto licenza **MIT**. Libero per uso, modifica e distribuzione.

### Crediti

- Il tracciato vettoriale del controller **DualSense Edge** (silhouette, scocca, tasti, levette, lightbar e paddle) è derivato dal progetto [daidr/dualsense-tester](https://github.com/daidr/dualsense-tester), distribuito sotto licenza **MIT**. I colori, i gradienti, le ombreggiature e le texture sono stati ridisegnati per questa applicazione.
- Il protocollo HID del DualSense (report `0x01`/`0x31`, output `0x02`/`0x31`, CRC Bluetooth) è documentato pubblicamente dalla community (progetti `dualsense-ctl`, `hid-playstation` del kernel Linux e `SDL`).
