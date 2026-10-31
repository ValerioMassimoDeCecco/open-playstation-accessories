# PlayStation Accessories - Open Source Edition 🎮

Un clone **open-source**, leggero, moderno e privo di telemetria dell'applicazione ufficiale **Sony PlayStation Accessories** per PC Windows, progettato per gestire sia il controller **DualSense** standard che il controller avanzato **DualSense Edge**.

---

## 🌟 Caratteristiche Principali

- **100% Hardware Reale Diretto**: Zero modalità demo o simulazioni fittizie. Comunica direttamente con l'hardware fisico del tuo DualSense (`PID 0x0CE6`) o DualSense Edge (`PID 0x0DF2`) collegato sia via **Cavo USB** che via **Bluetooth**.
- **Rilevamento a Caldo (Hot-Plug)**: Monitora costantemente la connessione; se colleghi o scolleghi il controller o passi da cavo a Bluetooth, viene rilevato all'istante.
- **Zero Dipendenze Esterne**: Funziona con l'interprete Python 3 standard installato su Windows. Non richiede librerie di terze parti o pip wheels (interagisce con le API native Windows a 64-bit `SetupAPI.dll`, `HID.dll` e `Kernel32.dll` direttamente via `ctypes`).
- **Nessuna Telemetria o Tracking**: A differenza dell'app proprietaria ufficiale (che include un intero motore JavaScriptCore + libcurl per inviare diagnostiche e fingerprinting hardware alla pipeline Sony S-Bahn), questo clone è locale al 100%.
- **Tester Interattivo Live in Tempo Reale**:
  - Visualizzazione grafica e reattiva di tutti i pulsanti (✕, ◯, ▢, △, D-Pad, L1, R1, L2, R2, L3, R3, Create, Options, PS, Touchpad, Fn e Paddle posteriori).
  - Radar a cerchio con reticolo delle levette analogiche (coordinate esatte, deviazione e cerchio della deadzone interna).
  - Indicatori di pressione progressiva dei grilletti L2 ed R2 (0-255).
  - Test rapido dei motori del feedback aptico / vibrazione.
  - Indicatore di stato batteria e carica.
- **Gestore Profili Avanzato DualSense Edge**:
  - **Curve di Sensibilità Ufficiali con rendering matematico in tempo reale**:
    - *Lineare (Standard 1:1)*
    - *Rapido (Quick)* - accelerazione immediata per shooter frenetici.
    - *Preciso (Precise)* - micro-correzioni per cecchini e mira a lungo raggio.
    - *Costante (Steady)* - traiettorie stabili per giochi d'azione.
    - *Digitale (Digital)* - output istantaneo al 100% per picchiaduro.
    - *Dinamico (Dynamic)* - curva sigmoidale S-Curve.
  - Regolazione fine delle zone morte (*deadzone*) e anti-deadzone.
  - Regolazione della soglia dei grilletti (*Hair-Trigger* / corsa minima).
  - Rimappatura completa dei tasti posteriori (*Back Paddles LB / RB*).
- **Assegnazione Slot Profilo (Scorciatoie Fn)**:
  - Interfaccia visuale che replica gli slot hardware del controller:
    - **Slot 1**: `Fn + △`
    - **Slot 2**: `Fn + ◯`
    - **Slot 3**: `Fn + ✕`
    - **Slot 4**: `Fn + ▢`
- **Controllo Barra Luminosa (RGB Lightbar) & Player LED**:
  - Color picker interattivo e preset rapidi (PlayStation Blue, Cyber Cyan, Crimson Red, Neon Green, Royal Violet, Solar Gold, Pure White).
  - Invio dei comandi di output HID reali per cambiare i colori dei LED sul controller fisico.

---

## 🚀 Come Avviare l'Applicazione

### Metodo 1: Collegamento sul Desktop
Fai doppio click su:
👉 **`Avvia PlayStation Accessories`** (sul tuo Desktop, nella cartella `Programmi`).

### Metodo 2: File Batch Diretto
Fai doppio click su `run.bat` dentro `C:\Users\Valerio\Desktop\Programmi\PlayStationAccessories\`.

### Metodo 3: Da Terminale (PowerShell / Command Prompt)
```powershell
cd "C:\Users\Valerio\Desktop\Programmi\PlayStationAccessories"
python app\main.py
```

L'applicazione aprirà automaticamente il browser all'indirizzo:
👉 **`http://127.0.0.1:8080`**

---

## 📐 Architettura del Progetto

```
PlayStationAccessories/
├── app/
│   ├── controller/
│   │   ├── hid_windows.py    # Wrapper nativo Windows HID a 64-bit (SetupAPI.dll / HID.dll via ctypes)
│   │   └── dualsense.py      # Parser pacchetti HID hardware DualSense (0x01/0x31) & output report (0x02/0x31)
│   ├── profiles/
│   │   └── manager.py        # Gestione profili JSON, curve matematiche e slot Fn
│   ├── web/
│   │   ├── server.py         # Server HTTP REST nativo (ThreadingHTTPServer)
│   │   └── static/
│   │       ├── index.html    # Dashboard PS5 Fluent Dark
│   │       ├── style.css     # Design responsive, SVG interattivo del controller
│   │       └── app.js        # Polling real-time, canvas radar e controlli
│   └── main.py               # Hot-plug hardware supervisor & lifecycle
├── profiles.json             # Archivio profili e configurazioni salvate
├── run.bat                   # Launcher rapido Windows
└── README.md                 # Documentazione del progetto
```

---

## ⚖️ Licenza
Distribuito sotto licenza **MIT**. Libero per uso, modifica e distribuzione.
