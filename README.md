# Mockup Marasca

Due strumenti per provare un'etichetta d'olio su una bottiglia in 3D.

Sito: https://mockup-marasca.vercel.app  ·  Repository: https://github.com/552020/mockup-marasca
Ogni push su `main` aggiorna il sito.

## 1. WebGL, nel browser (immediato)

`index.html` è la pagina: online su Vercel (vedi sotto) oppure in locale con un doppio clic (serve la connessione per scaricare la libreria Three.js).

Etichetta: pulsante «Carica la tua etichetta», oppure trascina il PNG sulla bottiglia, oppure copia in Photoshop e incolla con ⌘V.
L'altezza in mm segue le proporzioni dell'immagine; regola larghezza e distanza dal fondo.

Bottiglia: parti da Marasca 250/500/750 o Dorica 500 e modifica Ø corpo, altezza, Ø collo, corpo dritto, spalla e forma della spalla.
Ogni modifica passa a «Personalizzata».
Tappo: nero, oro, argento o un colore a scelta (anche metallico). Spunte per il collo dritto senza anello e per togliere il beccuccio sopra il tappo.

La vostra bottiglia: trascina un file GLB, OBJ o STL (il modello del vetraio, o un'esportazione da Blender o dal CAD).
La pagina rileva l'altezza e l'unità di misura, misura il diametro e la zona dritta, e avvolge l'etichetta sul diametro reale.
Se l'altezza non torna, correggila nel campo «Altezza reale»; se la bottiglia appare sdraiata, spunta «L'asse verticale del file è Z».

## 1b. Dal sito a Blender con un clic

Nella pagina, sezione «Per Blender», il pulsante «Scarica il file per Blender» produce `mockup-marasca-blender.txt`:
un solo file con dentro bottiglia, quote, tappo, etichetta e, se caricata, la bottiglia da file.
In Blender: area Scripting → menu Testo → Apri → scegli il file → Esegui script. La scena compare con vetro, olio, luci e camera.
Da Terminale, per il render diretto:

    /Applications/Blender.app/Contents/MacOS/Blender -b -P mockup-marasca-blender.txt

`esempio-scaricato-dal-sito.txt` è un file di questo tipo, prodotto durante le prove.
Sul sito il file si scarica direttamente. Nella versione su claude.ai il salvataggio ha dei limiti: in quel caso la pagina mostra il testo da copiare e incollare nell'editor di testo di Blender.

## 2. Blender + Cycles, fotorealistico

Serve Blender 4.x (gratuito): https://www.blender.org/download/ oppure `brew install --cask blender`.

Render da Terminale, senza aprire l'interfaccia:

    /Applications/Blender.app/Contents/MacOS/Blender -b -P marasca_mockup.py -- \
        --label etichetta.png --label-width 90 --label-bottom 32 --out render.png

Prova rapida (10 secondi su Apple Silicon):

    ... -- --label etichetta.png --res 700 875 --samples 48 --out prova.png

Immagine finale per una presentazione (qualche minuto):

    ... -- --label etichetta.png --res 2400 3000 --samples 512 --out finale.png

Per aprire la scena in Blender e lavorarci a mano:

    /Applications/Blender.app/Contents/MacOS/Blender -P marasca_mockup.py -- --label etichetta.png --no-render

Opzioni utili:

    --bottle marasca250 | marasca500 | marasca750 | dorica500
    --glass verde | trasparente | ambra
    --cap nero | oro | argento
    --cap-color '#7a1f1f'   colore del tappo a scelta; aggiungi --cap-metal per la finitura metallica
    --neck dritto           collo dritto senza anello (default: anello)
    --no-spout              tappo senza beccuccio versatore
    --diameter 63 --height 271 --body 168 --shoulder 15 --shoulder-shape 2.4 --neck-diameter 31.5
                            quote a scelta (--bottle custom)
    --model bottiglia.glb --model-height 271   bottiglia da file GLB, OBJ o STL
    --finish opaca | lucida
    --back retro.png --back-width 60
    --angle 0            camera frontale (default 18 gradi)
    --transparent        PNG con sfondo trasparente da montare in Photoshop
    --view AgX           resa più fotografica (default Standard: colori dell'etichetta fedeli)
    --save-blend scena.blend

## Resa realistica

La pagina WebGL serve a giudicare proporzioni e leggibilità. Per l'immagine fotografica usa lo script Blender:
`render-esempio-collo-dritto.png` è stato prodotto con

    ... -- --label etichetta.png --neck dritto --no-spout --cap-color '#7a1f1f' --glass trasparente --res 2400 3000 --samples 512

## Etichetta

Esporta da Photoshop in PNG (con trasparenza se fustellata) o JPG, sRGB.
Le proporzioni dell'immagine vengono rispettate: l'altezza in mm segue la larghezza.
Marasca 500 ml: corpo Ø 63 mm, circonferenza 198 mm, zona etichettabile alta 168 mm.
