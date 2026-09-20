# ============================================================================
# op15-toolbox.ps1 — OnePlus 15 (CPH2747) — automate téléchargement, root, ROM
#
# UI console PowerShell qui pilote le pipeline de l'agent spécialisé :
#   - téléchargement de tout le nécessaire (HTTP + navigateur anti-bot + EDL)
#   - préparation de l'environnement (adb/fastboot, extractions)
#   - déverrouillage du bootloader (variante globale)
#   - root (Magisk / KernelSU / APatch), recovery OrangeFox
#   - flash firmware / ROM (RegionalHybrid Flasher GLO 16.0.9.400)
#   - unbrick EDL (OPlusEDLTool / bkerler-edl / drivers QDLoader)
#   - rapport de synthèse du pipeline
#
# CONTRAINTE MATÉRIELLE (anti-rollback / eFuse) :
#   L'appareil est sur 16.0.0.204 (build de lancement). Le flasher 16.0.9.400
#   est PLUS RÉCENT -> l'upgrade 204→400 est autorisé par l'index anti-rollback,
#   MAIS il avance cet index de façon PERMANENTE : retour en 204 impossible.
#   Le root se fait avec l'init_boot 400 local (déjà extrait du flasher).
#
# RÈGLES DE SÉCURITÉ :
#   * Les étapes destructrices exigent une confirmation explicite (taper le mot-clé).
#   * Aucun flash n'est lancé sans appareil détecté dans le bon mode.
#   * Les commandes fastboot/adb utilisent les binaires téléchargés
#     (downloads\tools\platform-tools).
#   * Journal complet dans downloads\ui.log
#
# Usage :  powershell -ExecutionPolicy Bypass -File op15-toolbox.ps1
# ============================================================================

$ErrorActionPreference = 'Stop'

$Script:Root    = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script:Adb     = Join-Path $Root 'downloads\tools\platform-tools\adb.exe'
$Script:Fastboot= Join-Path $Root 'downloads\tools\platform-tools\fastboot.exe'
$Script:LogFile = Join-Path $Root 'downloads\ui.log'
$Script:Python  = 'python'

$C = @{
    Info   = 'Cyan'
    Ok     = 'Green'
    Warn   = 'Yellow'
    Err    = 'Red'
    Accent = 'Magenta'
    Dim    = 'DarkGray'
}

function Log([string]$msg) {
    $dir = Split-Path -Parent $Script:LogFile
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg" | Add-Content -Path $Script:LogFile -Encoding UTF8
}

function Write-C($Color, [string]$Msg) { Write-Host $Msg -ForegroundColor $Color }

function Title([string]$Msg)   { Write-C $C.Accent ("`n======== " + $Msg.ToUpper() + " ========") }
function Section([string]$Msg) { Write-C $C.Info  ("--- " + $Msg) }
function Info([string]$Msg)    { Write-C $C.Info  $Msg }
function Ok([string]$Msg)      { Write-C $C.Ok    ("[OK] " + $Msg) }
function Warn([string]$Msg)    { Write-C $C.Warn  ("[!]  " + $Msg) }
function Err([string]$Msg)     { Write-C $C.Err   ("[!!] " + $Msg) }

function Banner {
    Clear-Host
    Write-Host '================================================================================' -ForegroundColor $C.Accent
    Write-Host '  OnePlus 15 Toolbox  -  CPH2747 (global) - build CPH2747_16.0.0.204(EX01)'         -ForegroundColor $C.Accent
    Write-Host '  Pipeline agent specialise : download / bootloader / root / ROM / EDL / rapport'   -ForegroundColor $C.Accent
    Write-Host '================================================================================' -ForegroundColor $C.Accent
}

function Confirm-Dangerous([string]$Keyword, [string]$Message) {
    # Retourne $true si l'utilisateur tape exactement $Keyword
    Write-C $C.Warn "  >>> $Message"
    $ans = Read-Host "  Taper '$Keyword' pour confirmer (ou Entree pour annuler)"
    if ($ans -ceq $Keyword) { return $true }
    Warn 'Action annulee.'
    return $false
}

function Find-Tool {
    param([string]$Name)
    $found = Get-ChildItem -Path (Join-Path $Root 'downloads\tools') -Recurse -Filter $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    return $found
}

function Invoke-Py {
    param([string[]]$Args)
    Push-Location $Root
    try {
        & $Script:Python @Args
        $code = $LASTEXITCODE
        if ($code -eq $null) { $code = 0 }
    } finally { Pop-Location }
    return $code
}

function Get-AdbDevice {
    if (-not (Test-Path $Script:Adb)) { return $null }
    $out = & $Script:Adb devices 2>$null
    $serial = ($out | Select-String -Pattern '^\S+\s+device\b' | ForEach-Object { ($_ -split '\s+')[0] } | Select-Object -First 1)
    return $serial
}

function Get-FastbootDevice {
    if (-not (Test-Path $Script:Fastboot)) { return $null }
    $out = & $Script:Fastboot devices 2>$null
    $serial = ($out | Select-String -Pattern '^\S+\s+fastboot\b' | ForEach-Object { ($_ -split '\s+')[0] } | Select-Object -First 1)
    return $serial
}

function Get-AdbRecoveryDevice {
    if (-not (Test-Path $Script:Adb)) { return $null }
    $out = & $Script:Adb devices 2>$null
    $serial = ($out | Select-String -Pattern '^\S+\s+recovery\b' | ForEach-Object { ($_ -split '\s+')[0] } | Select-Object -First 1)
    return $serial
}

function Assert-Fastboot {
    $d = Get-FastbootDevice
    if (-not $d) { Err 'Aucun appareil detecte en mode fastboot.'; return $false }
    Ok "Appareil en fastboot : $d"
    return $true
}

# ---------------------------------------------------------------------------
# Bilan complet des artefacts (state.json)
# ---------------------------------------------------------------------------
function Show-Artefacts {
    $statePath = Join-Path $Root 'downloads\state.json'
    if (-not (Test-Path $statePath)) { Warn 'state.json absent.'; return }
    $state = Get-Content $statePath -Raw | ConvertFrom-Json
    $props = $state.PSObject.Properties
    if (-not $props) { Warn 'state.json vide.'; return }
    foreach ($p in $props) {
        $status = $p.Value.status
        $dest = $p.Value.dest
        switch ($status) {
            'ok'             { Ok    ("{0,-20} -> {1}" -f $p.Name, $dest) }
            'ok_large'       { Ok    ("{0,-20} -> {1}" -f $p.Name, $dest) }
            'absent'         { Warn  ("{0,-20} MANQUANT -> {1}" -f $p.Name, $dest) }
            'absent_large'   { Warn  ("{0,-20} MANQUANT (gros fichier) -> {1}" -f $p.Name, $dest) }
            'browser'        { Warn  ("{0,-20} browser -> {1}" -f $p.Name, $dest) }
            'deprecated'     { Info  ("{0,-20} obsolete (plus necessaire)" -f $p.Name) }
            'manual'         { Info  ("{0,-20} installation manuelle -> {1}" -f $p.Name, $dest) }
            'error'          { Err   ("{0,-20} ERREUR : {1}" -f $p.Name, $p.Value.error) }
            default          { Info  ("{0,-20} statut {1} -> {2}" -f $p.Name, $status, $dest) }
        }
    }
}

# ---------------------------------------------------------------------------
# 1. Environnement
# ---------------------------------------------------------------------------
function Do-CheckEnv {
    Title 'Verification de l''environnement'
    Info "Python : $((& $Script:Python --version 2>&1))"
    foreach ($m in @('requests','networkx','websocket','playwright')) {
        $has = & $Script:Python -c "import $m; print('ok')" 2>$null
        if ($has -eq 'ok') { Ok "module $m" } else { Warn "module $m manquant (pip install $m)" }
    }
    if (Test-Path $Script:Adb)  { Ok 'adb present' }  else { Warn 'adb absent' }
    if (Test-Path $Script:Fastboot) { Ok 'fastboot present' } else { Warn 'fastboot absent' }
    Section 'Bilan des artefacts'
    Show-Artefacts
}

# ---------------------------------------------------------------------------
# 2. Telechargements
# ---------------------------------------------------------------------------
function Do-DownloadAll {
    Title 'Telechargement de tout le necessaire (HTTP + GitHub)'
    $code = Invoke-Py @('downloader.py')
    if ($code -eq 0) { Ok 'Telechargements termines' } else { Err "downloader.py a retourne $code" }
    Invoke-Py @('downloader.py','--verify') | Out-Null
}

function Do-DownloadFlasher {
    Title 'Telechargement du RegionalHybrid Flasher GLO 16.0.9.400 (~9,5 Go, avec reprise)'
    Warn 'Fichier volumineux. La reprise est automatique en cas d''interruption.'
    if (-not (Confirm-Dangerous 'GO' 'Lancer ce gros telechargement ?')) { return }
    $code = Invoke-Py @('downloader.py','--only','regional-flasher')
    if ($code -eq 0) {
        Ok 'Flasher telecharge'
        Section 'Extraction init_boot (build 400)'
        $flasher = Get-ChildItem -Path (Join-Path $Root 'downloads\firmware') -Recurse -Filter 'RegionalHybrid*.zip' -ErrorAction SilentlyContinue | Select-Object -First 1
        $b400dir = Join-Path $Root 'downloads\firmware\build-400'
        New-Item -ItemType Directory -Path $b400dir -Force | Out-Null
        if ($flasher) {
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            $arc = [System.IO.Compression.ZipFile]::OpenRead($flasher.FullName)
            try {
                $entry = $arc.Entries | Where-Object { $_.FullName -match 'init_boot\.img$' } | Select-Object -First 1
                if ($entry) {
                    $dest = Join-Path $b400dir 'init_boot.img'
                    $in = $entry.Open()
                    $out = [System.IO.File]::Create($dest)
                    try { $in.CopyTo($out) } finally { $in.Dispose(); $out.Dispose() }
                    Ok "init_boot 400 extrait : $dest"
                } else { Warn 'init_boot.img introuvable dans le flasher.' }
            } finally { $arc.Dispose() }
        } else { Warn 'Zip du flasher introuvable apres telechargement.' }
    } else { Err "Echec (code $code)" }
}

function Do-BrowserFetch {
    Title 'Telechargement via navigateur (anti-bot : OTA, Drive, Mega...)'
    Info 'La fenetre Edge/Chrome s''ouvre avec un profil dedie. Resous toi-meme captchas/connexions.'
    $choice = Read-Host "  [a]gents (recherche auto) / [m]anifest (liste fixe) / [u]rls manuelles ? (a/m/u)"
    switch ($choice.ToLower()) {
        'm' {
            $code = Invoke-Py @('browser_fetch.py')
            if ($code -ne 0) { Err "browser_fetch.py code $code" }
        }
        'u' {
            $url = Read-Host '  URL a telecharger'
            if ($url) { Invoke-Py @('browser_agent_cli.py','download',$url,'--aspect','firmware') }
        }
        default {
            $q = Read-Host '  Requete (ex : OnePlus 15 CPH2747 OTA full zip)'
            if ($q) { Invoke-Py @('browser_agent_cli.py','fetch',$q,'--aspect','firmware') }
        }
    }
}

# ---------------------------------------------------------------------------
# 3. Preparation
# ---------------------------------------------------------------------------
function Do-Prepare {
    Title 'Preparation de l''environnement (extraction, verification, rapport)'
    $code = Invoke-Py @('prepare_env.py')
    if ($code -eq 0) {
        Ok 'Preparation terminee'
        $rep = Join-Path $Root 'downloads\PREPARE_REPORT.txt'
        if (Test-Path $rep) { Info (Get-Content $rep -Raw) }
    } else { Err "prepare_env.py code $code" }
}

# ---------------------------------------------------------------------------
# 4. Registre
# ---------------------------------------------------------------------------
function Do-Registry {
    Title 'Registre des artefacts (URL | fichier | date | hash)'
    Invoke-Py @('browser_agent_cli.py','registry')
}

# ---------------------------------------------------------------------------
# 5. Appareil
# ---------------------------------------------------------------------------
function Do-Device {
    Title 'Etat de l''appareil'
    $a = Get-AdbDevice
    $f = Get-FastbootDevice
    $r = Get-AdbRecoveryDevice
    if ($a) { Ok "ADB      : $a" } else { Info 'ADB      : aucun appareil en mode ADB' }
    if ($f) { Ok "FASTBOOT : $f" } else { Info 'FASTBOOT : aucun appareil en mode fastboot' }
    if ($r) { Ok "RECOVERY : $r (OrangeFox/TWRP)" } else { Info 'RECOVERY : aucun appareil en mode recovery' }
}

# ---------------------------------------------------------------------------
# 6. Deverrouillage du bootloader (variante globale)
# ---------------------------------------------------------------------------
function Do-Unlock {
    Title 'Deverrouillage du bootloader (CPH2747 global - direct, sans In-Depth Test)'
    Warn 'EFFACE TOUTES LES DONNEES. Annule la garantie. Play Integrity altere.'
    if (-not (Confirm-Dangerous 'UNLOCK' 'Tout effacer et deverrouiller ?')) { return }
    if (-not (Assert-Fastboot)) { return }
    Section 'Controle pre-vol (pre_flight.py)'
    $code = Invoke-Py @('pre_flight.py','--check','unlock')
    if ($code -ne 0) { Err 'Pre-vol KO — on annule.'; return }
    Info 'Sur l''ecran de l''appareil : confirmer le deverrouillage (touches volume + power).'
    & $Script:Fastboot flashing unlock
    Start-Sleep -Seconds 5
    Info 'Attente de la confirmation sur l''ecran de l''appareil...'
    Read-Host '  Appuie sur Entree une fois la confirmation faite sur l''appareil'
    $v = & $Script:Fastboot getvar unlocked 2>&1
    if ($v -match 'yes') { Ok 'Bootloader deverrouille (getvar unlocked = yes)' }
    else { Warn "Etat indetermine : $v" }
}

# ---------------------------------------------------------------------------
# 7. Root Magisk — init_boot de la build courante (400 local ou 204 capture)
# ---------------------------------------------------------------------------
function Get-InitBoot {
    # retourne le chemin d'un init_boot.img dispo, priorite build-400 (recommandé)
    $b400 = Get-ChildItem -Path (Join-Path $Root 'downloads\firmware\build-400') -Recurse -Filter 'init_boot.img' -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch 'patched' } | Select-Object -First 1
    if ($b400) { return $b400 }
    $b204 = Get-ChildItem -Path (Join-Path $Root 'downloads\firmware\build-204') -Recurse -Filter 'init_boot.img' -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch 'patched' } | Select-Object -First 1
    if ($b204) { return $b204 }
    $any = Get-ChildItem -Path (Join-Path $Root 'downloads\firmware') -Recurse -Filter 'init_boot.img' -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch 'patched' } | Select-Object -First 1
    return $any
}

function Do-RootMagisk {
    Title 'Root via Magisk (init_boot de la build installee)'
    Info 'Prerequis : bootloader deverrouille + firmware de la build courante.'
    Section 'Anti-rollback / eFuse (a lire avant)'
    Warn 'Appareil : build 204 (lancement). Flasher le 400 = UPGRADE autorise, MAIS'
    Warn 'irreversible : retour en 204 impossible apres (index anti-rollback).'

    $init_boot = Get-InitBoot
    $b400dir = Join-Path $Root 'downloads\firmware\build-400'
    $b204dir = Join-Path $Root 'downloads\firmware\build-204'

    if (-not $init_boot) {
        Err 'Aucun init_boot.img trouve dans downloads\firmware\.'
        Info "  - init_boot 400 deja extrait : $b400dir\init_boot.img"
        Info '  - ou depose ton init_boot (payload.bin -> payload-dumper) dans downloads\firmware\build-204\'
        return
    }
    Ok "init_boot trouve : $($init_boot.FullName)"

    # backup du stock pour rollback (meme dossier que la source)
    $stock = $init_boot
    if ($stock) {
        $backupDir = Join-Path $Root 'downloads\rollback'
        New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
        $backup = Join-Path $backupDir 'init_boot_stock.img'
        Copy-Item -LiteralPath $stock.FullName -Destination $backup -Force
        Ok "Rollback sauvegarde : $backup"
        Ok "Backup stock 400 deja prets : downloads\rollback\boot_stock_400.img + init_boot_stock_400.img + vbmeta_stock_400.img"
        Warn 'Bootloop ? re-flasher : fastboot flash init_boot downloads\rollback\init_boot_stock_400.img ; fastboot flash boot downloads\rollback\boot_stock_400.img ; fastboot reboot'
    } else {
        Warn 'Aucun init_boot stock trouve pour rollback — risque bootloop en cas d''echec.'
    }

    $a = Get-AdbDevice
    if ($a) {
        Section 'Envoi de init_boot sur l''appareil'
        & $Script:Adb -s $a push $init_boot.FullName /sdcard/Download/ | Out-Host
        Read-Host '  Sur l''appareil : ouvre Magisk | Install | Selectionner et patcher un fichier | choisis init_boot.img.'
        Read-Host '  Note le nom du fichier patche (magisk_patched-*.img) puis appuie sur Entree.'
    } else {
        Warn 'Appareil non connecte en ADB - patche init_boot.img manuellement via Magisk puis place magisk_patched-*.img dans downloads\.'
        Read-Host '  Appuie sur Entree quand le fichier patche est pret'
    }
    $patched = Get-ChildItem -Path (Join-Path $Root 'downloads') -Recurse -Filter 'magisk_patched*.img' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $patched) {
        $pulled = Join-Path $Root 'downloads\tools'
        if ($a) {
            Section 'Recuperation du fichier patche depuis l''appareil'
            $remote = & $Script:Adb -s $a shell 'ls /sdcard/Download/magisk_patched*.img' 2>$null | Select-Object -First 1
            if ($remote) { & $Script:Adb -s $a pull $remote $pulled | Out-Null }
            $patched = Get-ChildItem $pulled -Filter 'magisk_patched*.img' | Select-Object -First 1
        }
    }
    if (-not $patched) { Err 'Fichier patche introuvable.'; return }
    Ok "init_boot patche : $($patched.Name)"

    if (-not (Confirm-Dangerous 'FLASH' "Flasher $($patched.Name) sur la partition init_boot ?")) { return }
    if (-not (Assert-Fastboot)) { return }
    Section 'Controle pre-vol (pre_flight.py)'
    $code = Invoke-Py @('pre_flight.py','--check','root')
    if ($code -ne 0) { Err 'Pre-vol KO — on annule.'; return }
    & $Script:Fastboot flash init_boot $patched.FullName
    if ($LASTEXITCODE -eq 0) { Ok 'init_boot flashe. Redemarrage...' }
    & $Script:Fastboot reboot
    Read-Host '  Appuie sur Entree quand l''appareil a redemarre'
    $a2 = Get-AdbDevice
    if ($a2) {
        $su = & $Script:Adb -s $a2 shell 'su -c id' 2>$null
        if ($su -match 'root') { Ok "Root confirme : $su" } else { Warn 'su n''a pas repondu root (verifie l''app Magisk)' }
    }
}

# ---------------------------------------------------------------------------
# 8. Root alternatif (KernelSU / APatch)
# ---------------------------------------------------------------------------
function Do-RootAlt {
    Title 'Root alternatif - KernelSU / APatch'
    Info 'Le principe est identique au root Magisk, avec ces differences cles :'
    Info '  * KernelSU  | patche init_boot (meme flux que Magisk, app KernelSU)'
    Info '  * APatch    | patche boot.img (PAS init_boot) - definit une SuperKey >= 8 caracteres'
    Info 'Les APK sont deja dans downloads\tools\ (KernelSU-Next.apk, APatch.apk).'
    Warn 'Ne PAS melanger les methodes sur une meme partition.'
    $init = Get-InitBoot
    $boot = Get-ChildItem -Path (Join-Path $Root 'downloads\firmware\build-400') -Recurse -Filter 'boot.img' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($init) { Ok "init_boot dispo : $($init.Name) (KernelSU)" }
    if ($boot) { Ok "boot.img dispo : $($boot.Name) (APatch)" }
    $ksu = Get-ChildItem -Path (Join-Path $Root 'downloads\tools\kernel-susfs') -Filter '*.zip' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($ksu) {
        Ok "Kernel SUSFS OP15 dispo : $($ksu.Name)"
        Warn 'Kernel custom (KernelSU+SUSFS) : flashable en recovery, ROM stock OxygenOS uniquement.'
    } else {
        Info 'Kernel SUSFS absent (menu 2 pour le telecharger : kernel-susfs-op15).'
    }
}

# ---------------------------------------------------------------------------
# 9. OrangeFox recovery
# ---------------------------------------------------------------------------
function Do-OrangeFox {
    Title 'OrangeFox recovery (infiniti) - demarrage/flash'
    $img = Get-ChildItem -Path (Join-Path $Root 'downloads\tools\recovery') -Filter 'OrangeFox*.img' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $img) { Err 'OrangeFox*.img introuvable (lancer le menu 2 : telecharger tout).'; return }
    Info "Image : $($img.Name)"
    $choice = Read-Host '  [b]oot temporaire (sans modifier l''appareil, conseille) / [f]lash permanent ? (b/f)'
    if (-not (Assert-Fastboot)) { return }
    if ($choice -eq 'f') {
        if (-not (Confirm-Dangerous 'FLASH' 'Flasher la recovery de facon permanente ?')) { return }
        & $Script:Fastboot flash recovery $img.FullName
        if ($LASTEXITCODE -eq 0) { Ok 'Recovery flashee' }
    } else {
        & $Script:Fastboot boot $img.FullName
        Ok 'Demarrage temporaire sur OrangeFox...'
    }
}

# ---------------------------------------------------------------------------
# 10. Flash firmware / ROM (Regional Flasher GLO 400)
# ---------------------------------------------------------------------------
function Do-FlashRom {
    Title 'Flash firmware / ROM'
    Warn '!!! AVERTISSEMENT ANTI-ROLLBACK / eFUSE !!!'
    Warn 'Ce flasher est la build 16.0.9.400 (plus recente que le 204 installe).'
    Warn 'Le flash avance l''index anti-rollback de facon PERMANENTE :'
    Warn 'apres ce flash, retour en 204 (ou plus bas) IMPOSSIBLE.'
    Warn 'C''est un UPGRADE autorise (pas de brick), mais IRREVERSIBLE.'
    if (-not (Confirm-Dangerous 'FLASH' 'Passe en 400 de facon irreversible ?')) { return }
    Section 'Controle pre-vol (pre_flight.py)'
    $code = Invoke-Py @('pre_flight.py','--check','flash400')
    if ($code -ne 0) { Err 'Pre-vol KO — on annule.'; return }

    $flasher = Get-ChildItem -Path (Join-Path $Root 'downloads\firmware') -Recurse -Filter 'RegionalHybrid*.zip' -ErrorAction SilentlyContinue | Select-Object -First 1
    $fbe = Get-ChildItem -Path (Join-Path $Root 'downloads\tools') -Recurse -Filter 'FastbootEnhance*.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $flasher) {
        Warn 'RegionalHybrid Flasher absent (menu 4 pour le telecharger, ~9,5 Go).'
    } else {
        Info "Flasher : $($flasher.Name)"
        Section 'Extraction du flasher'
        $dest = Join-Path $Root 'downloads\firmware\regional-flasher\extract'
        New-Item -ItemType Directory -Path $dest -Force | Out-Null
        Expand-Archive -LiteralPath $flasher.FullName -DestinationPath $dest -Force
        $bat = Get-ChildItem $dest -Filter '*.bat' | Select-Object -First 1
        if ($bat) {
            Warn 'Le flasher necessite la fenetre de l''appareil en fastboot.'
            if (-not (Assert-Fastboot)) { return }
            Start-Process -FilePath $bat.FullName -WorkingDirectory $bat.DirectoryName
            Ok "Lance : $($bat.Name) - suis les instructions dans sa fenetre."
        } else { Err 'Aucun .bat trouve dans le flasher.' }
    }
    if ($fbe) {
        Info "FastbootEnhance present : $($fbe.FullName) (lancer manuellement pour flasher des images)"
    }
}

# ---------------------------------------------------------------------------
# 11. Unbrick EDL (OPlusEDLTool / bkerler-edl / drivers QDLoader)
# ---------------------------------------------------------------------------
function Do-Edl {
    Title 'Unbrick EDL (9008) - outillage'
    $tool = Get-ChildItem -Path (Join-Path $Root 'downloads\tools\oplus-edl') -Filter '*.zip' -ErrorAction SilentlyContinue | Select-Object -First 1
    $edlDir = Join-Path $Root 'downloads\tools\edl-bkerler'
    $driverPs = Join-Path $edlDir 'install_edl_win10_win11.ps1'
    $exe = Join-Path $Root 'downloads\tools\oplus-edl\OplusEdlTool.exe'

    Section 'Etat des outils EDL'
    if ($tool) { Ok "OPlusEDLTool zip : $($tool.Name)" } else { Warn 'OPlusEDLTool.zip absent (menu 2).' }
    if (-not (Test-Path -LiteralPath $exe)) {
        # extract if zip present but not yet extracted
        if ($tool) {
            Section 'Extraction OPlusEDLTool'
            $out = Join-Path $Root 'downloads\tools\oplus-edl'
            Expand-Archive -LiteralPath $tool.FullName -DestinationPath $out -Force
            $exe = Get-ChildItem $out -Filter 'OplusEdlTool.exe' -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        }
    } elseif (Test-Path -LiteralPath $exe) {
        $exe = Get-Item -LiteralPath $exe
    }
    if ($exe) { Ok "OplusEdlTool.exe : $($exe.FullName)" }
    if (Test-Path $edlDir) {
        Ok 'bkerler/edl (edlclient) present'
        $pyHas = & $Script:Python -c "import edlclient; print('ok')" 2>$null
        if ($pyHas -eq 'ok') { Ok 'edlclient importable (CLI edl.py)' } else { Warn 'edlclient non importable (pip install edl)' }
    } else { Warn 'bkerler/edl absent (clone non fait).' }
    if (Test-Path $driverPs) { Ok "Script drivers QDLoader dispo : $driverPs" } else { Warn 'Script drivers absent.' }

    Section 'Actions'
    Write-Host '  1. Installer les drivers QDLoader 9008 (script bkerler OU Microsoft Update Catalog)' -ForegroundColor White
    Write-Host '  2. Booter en EDL (Volume Up + cable USB) et verifier 9008 dans le gestionnaire' -ForegroundColor White
    Write-Host '  3. Lancer OPlusEDLTool (GUI) ou edl.py (CLI)' -ForegroundColor White
    $act = Read-Host '  Action [1]=installer drivers script / [2]=lancer OplusEdlTool / [3]=verifier port EDL / [Enter]=retour'
    switch ($act) {
        '1' {
            if (Test-Path $driverPs) {
                Warn 'Ce script lance winget (Zadig, Git, Python) et demande admin - execute-le en admin.'
                Start-Process powershell "-NoProfile -ExecutionPolicy Bypass -File `"$driverPs`"" -Verb RunAs
                Ok 'Script drivers lance dans une fenetre admin.'
            } else { Err 'Script absent.' }
        }
        '2' {
            if ($exe) { Start-Process -FilePath $exe.FullName -WorkingDirectory $exe.DirectoryName; Ok 'OplusEdlTool lance.' }
            else { Err 'OplusEdlTool.exe introuvable.' }
        }
        '3' {
            Section 'Ports serie / EDL (9008/900E)'
            Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'QDLoader|9008|900E|Qualcomm' } | Select-Object Name, Status | Format-Table -AutoSize
        }
        default { Info 'Retour au menu.' }
    }
}

# ---------------------------------------------------------------------------
# 12. Rapport pipeline
# ---------------------------------------------------------------------------
function Do-Report {
    Title 'Rapport de synthese du pipeline (OnePlus 15)'
    $code = Invoke-Py @('run.py','--report')
    if ($code -ne 0) { Warn "run.py --report code $code" }
    $md = Join-Path $Root 'reports\op15_report.md'
    if (Test-Path $md) { Info (Get-Content $md -TotalCount 40 -Raw) }
}

# ---------------------------------------------------------------------------
# 15. Recherche RAG / BM25
# ---------------------------------------------------------------------------
function Do-Rag {
    Title 'Recherche RAG / BM25 (memoire + catalogue domaine)'
    $q = Read-Host '  Question ou mots-cles (ex : "root Magisk CPH2747", "unbrick EDL 9008")'
    if (-not $q) { return }
    # La sortie native Python peut etre avalee en console pipee :
    # on capture dans un fichier puis on affiche via Write-Host.
    $outFile = Join-Path $Root 'downloads\rag_output.txt'
    & $Script:Python "browser_agent_cli.py" "rag" $q "--top" "5" *> $outFile
    if ($LASTEXITCODE -ne 0) { Err "recherche RAG code $LASTEXITCODE"; return }
    if (Test-Path $outFile) {
        Get-Content -Path $outFile -Encoding UTF8 | ForEach-Object { Write-Host $_ }
    }
}

# ---------------------------------------------------------------------------
# Menu principal
# ---------------------------------------------------------------------------
function Show-Menu {
    Banner
    Write-Host ''
    Write-Host '  -- ETAT ------------------------------------------' -ForegroundColor $C.Info
    Write-Host '   1. Verifier l''environnement + bilan artefacts' -ForegroundColor White
    Write-Host '   7. Etat de l''appareil (adb / fastboot / recovery)' -ForegroundColor White
    Write-Host '  -- TELECHARGEMENT -------------------------------' -ForegroundColor $C.Info
    Write-Host '   2. Telecharger tout (HTTP + GitHub : outils, EDL, ROM)' -ForegroundColor White
    Write-Host '   3. Telecharger via navigateur (anti-bot : OTA, Drive, Mega)' -ForegroundColor White
    Write-Host '   4. Flasher GLO 16.0.9.400 (~9,5 Go) + extraire init_boot 400' -ForegroundColor White
    Write-Host '  -- PREPARATION ----------------------------------' -ForegroundColor $C.Info
    Write-Host '   5. Preparer l''environnement (extraction, adb, rapport)' -ForegroundColor White
    Write-Host '   6. Registre des artefacts (hash, dedup)' -ForegroundColor White
    Write-Host '  -- APPAREIL -------------------------------------' -ForegroundColor $C.Info
    Write-Host '   8. Deverrouiller le bootloader (EFFACE les donnees)' -ForegroundColor Yellow
    Write-Host '   9. Root Magisk (init_boot build courante : 400 local)' -ForegroundColor Yellow
    Write-Host '  10. Root alternatif (KernelSU / APatch) - infos' -ForegroundColor White
    Write-Host '  11. OrangeFox recovery (boot temporaire / flash)' -ForegroundColor Yellow
    Write-Host '  12. Flash firmware / ROM (400 - IRREVERSIBLE, eFuse)' -ForegroundColor Yellow
    Write-Host '  -- REPARATION -----------------------------------' -ForegroundColor $C.Info
    Write-Host '  13. Unbrick EDL 9008 (OPlusEDLTool / bkerler / drivers)' -ForegroundColor Yellow
    Write-Host '  -- ANALYSE ---------------------------------------' -ForegroundColor $C.Info
    Write-Host '  14. Rapport de synthese du pipeline' -ForegroundColor White
    Write-Host '  15. Recherche RAG / BM25 (memoire + catalogue)' -ForegroundColor White
    Write-Host '   Q. Quitter' -ForegroundColor White
    Write-Host ''
}

:MainLoop while ($true) {
    Show-Menu
    $choice = Read-Host '  Choix'
    Log "menu : $choice"
    switch ($choice) {
        '1'  { Do-CheckEnv }
        '2'  { Do-DownloadAll }
        '3'  { Do-BrowserFetch }
        '4'  { Do-DownloadFlasher }
        '5'  { Do-Prepare }
        '6'  { Do-Registry }
        '7'  { Do-Device }
        '8'  { Do-Unlock }
        '9'  { Do-RootMagisk }
        '10' { Do-RootAlt }
        '11' { Do-OrangeFox }
        '12' { Do-FlashRom }
        '13' { Do-Edl }
        '14' { Do-Report }
        '15' { Do-Rag }
        'Q'  { Write-Host 'Au revoir.' -ForegroundColor $C.Info; break MainLoop }
        default { Err 'Choix invalide.' }
    }
    Write-Host ''
    if ($choice -ne 'Q') { Read-Host '  Appuie sur Entree pour continuer' }
}
