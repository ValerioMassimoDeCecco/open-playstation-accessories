#!/bin/bash
# PlayStation Accessories - doppio click su macOS
cd "$(dirname "$0")" || exit 1
./run.sh "$@"
status=$?
if [ "$status" -ne 0 ]; then
    echo ""
    echo "L'applicazione e terminata con errori (codice $status)."
    read -r -p "Premi INVIO per chiudere questa finestra..."
fi
exit "$status"
