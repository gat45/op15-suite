"""
op15_domain.py — ontologie matériel OnePlus 15.

Source unique de vérité du domaine : modèles, partitions, outils, procédures,
composants matériels, risques, et les motifs regex associés.

Statut des procédures :
  - "verified"  : corroborée par plusieurs sources publiques indépendantes
  - "hypothesis": établie mais non confirmée sur appareil réel / communautaire
  - "in_progress" : développement en cours (pas encore stable)

Chaque procédure expose : aspect, steps (list[str]), risks (list[str]),
source_refs (list[str]), status, contract (comportement observable attendu).
"""

ASPECTS = ["bootloader", "root", "firmware", "reparation", "amelioration", "hardware"]

MODELS = {
    "CPH2745": {"region": "global", "firmware": "OxygenOS", "codename": "infiniti"},
    "CPH2747": {"region": "global/EU", "firmware": "OxygenOS", "codename": "infiniti"},
    "CPH2749": {"region": "Inde/US", "firmware": "OxygenOS", "codename": "infiniti"},
    "PLK110": {"region": "Chine", "firmware": "ColorOS", "codename": "infiniti"},
}

PARTITIONS = [
    "init_boot", "boot", "vbmeta", "dtbo", "vendor_boot", "recovery",
    "super", "efisp", "abl", "oplusreserve1", "persist", "boot_a", "boot_b",
]

TOOLS = [
    "adb", "fastboot", "fastbootd", "Magisk", "KernelSU", "APatch", "SukiSU",
    "MSM Download Tool", "OPlus Flash Tool", "OPLUS EDL Tool", "bkerler/edl",
    "payload-dumper", "Fastboot Enhance Tool", "Oxygen Updater", "OrangeFox",
    "TWRP", "avbroot", "DeepTestOP15", "In-Depth Test", "Zygisk", "Zygisk Next",
    "Shamiko", "Tricky Store", "Play Integrity Fix", "SUSFS", "ksu_susfs",
    "FrameworkPatcherGO", "avbroot", "GrapheneOS", "Shizuku", "Universal Android Debloater",
    "HideMyApplist", "bindhosts", "LSPosed",
]

PROCEDURES = {
    "bootloader_unlock_global": {
        "aspect": "bootloader",
        "steps": [
            "Activer options développeur + débogage USB + déverrouillage OEM",
            "adb reboot bootloader",
            "fastboot devices",
            "fastboot flashing unlock  (confirmer sur l'écran, reset complet)",
            "fastboot getvar unlocked  -> doit retourner yes",
        ],
        "risks": ["effacement total des données", "annulation garantie",
                  "Play Integrity altéré", "apps bancaires potentiellement bloquées"],
        "source_refs": ["droidwin.com/how-to-unlock-bootloader-on-oneplus-15-in-depth-test-app/",
                        "teamandroid.com/unlock-bootloader-oneplus",
                        "awesome-android-root how-to-unlock-bootloader.md"],
        "status": "verified",
        "contract": "Le bootloader passe de locked à unlocked, getvar unlocked=yes, reset data effectué.",
    },
    "bootloader_unlock_cn": {
        "aspect": "bootloader",
        "steps": [
            "Installer l'APK In-Depth Test (DeepTestOP15) + compte Heytap",
            "Appliquer -> soumettre la demande -> attendre ~24 h",
            "Après approbation : débogage USB + OEM unlock activés",
            "adb reboot bootloader -> fastboot flashing unlock -> confirmer",
        ],
        "risks": ["approbation refusée/retardée", "effacement total", "variantes opérateur non déverrouillables"],
        "source_refs": ["droidwin.com/how-to-unlock-bootloader-on-oneplus-15-in-depth-test-app/",
                        "ncunlock.com/oneplus-15-bootloader-unlock",
                        "bbsstatic.oneplus.com (APK 深度测试)"],
        "status": "verified",
        "contract": "Après approbation de l'app In-Depth Test, fastboot flashing unlock fonctionne sur PLK110.",
    },
    "root_magisk": {
        "aspect": "root",
        "steps": [
            "Obtenir le firmware exact du build installé",
            "Extraire payload.bin -> init_boot.img (payload-dumper/Fastboot Enhance Tool)",
            "adb push init_boot.img + patcher via l'app Magisk",
            "fastboot flash init_boot magisk_patched.img",
            "Magisk -> Require Additional Setup -> Direct Install -> reboot",
            "Vérifier : adb shell su -> id=uid=0(root)",
        ],
        "risks": ["bootloop si image du mauvais build", "OTA cassé après root",
                  "Play Integrity / apps bancaires"],
        "source_refs": ["droidwin.com/how-to-root-oneplus-15-via-magisk-kernelsu-apatch/",
                        "github.com/awesome-android-root ... how-to-root-oneplus-phone.md"],
        "status": "verified",
        "contract": "init_boot patché par Magisk => accès root persistant, TOKEN_BEGIN/END parseable.",
    },
    "root_kernelsu": {
        "aspect": "root",
        "steps": [
            "init_boot.img du build courant",
            "Patcher via l'app KernelSU (ou KernelSU Next)",
            "fastboot flash init_boot ksu_patched.img",
            "Vérifier via l'app KernelSU + adb shell su",
        ],
        "risks": ["pas de custom kernel KSU en date de collecte", "OTA à re-patch"],
        "source_refs": ["droidwin.com/how-to-root-oneplus-15-via-magisk-kernelsu-apatch/",
                        "kernelsu.org/guide/installation.html",
                        "xdaforums.com/t/how-to-root-oneplus-15-cph2749_16-0-2-401.4772839/"],
        "status": "verified",
        "contract": "KernelSU Next patche init_boot du slot actif => root kernel-level.",
    },
    "root_apatch": {
        "aspect": "root",
        "steps": [
            "boot.img (APatch n'utilise PAS init_boot)",
            "Patcher via l'app APatch + définir SuperKey (>=8 caractères)",
            "fastboot flash boot apatch_patched.img",
        ],
        "risks": ["boot.img (pas init_boot) — erreur courante", "superkey faible"],
        "source_refs": ["droidwin.com/how-to-root-oneplus-15-via-magisk-kernelsu-apatch/"],
        "status": "verified",
        "contract": "boot.img patché par APatch => root kernel + superkey requis.",
    },
    "root_fake_locked": {
        "aspect": "root",
        "steps": [
            "Déverrouiller le BL normalement (prérequis)",
            "Backup partition oplusreserve1 tant que BL ouvert",
            "Flasher ABL_with_superfastboot.efi sur efisp (ou module gbl_root_canoe)",
            "Rooter via init_boot patché, puis relocker le BL",
            "Après OTA : re-flasher pour conserver la version ABL",
        ],
        "risks": ["hardbrick si incompatibilité TEE", "OTA peut coincer au premier écran",
                  "données inaccessibles si état TEE incohérent", "méthode non supportée officiellement"],
        "source_refs": ["xdaforums.com/t/root-with-locked-bootloader-oneplus-15.4783161",
                        "github.com/superturtlee/gbl_root_canoe"],
        "status": "hypothesis",
        "contract": "BL verrouillé + root maintenu (fake locked). Non garanti ; exige ABL avec vulnérabilité GBL.",
    },
    "flash_fastboot_rom": {
        "aspect": "firmware",
        "steps": [
            "BL déverrouillé obligatoire",
            "Télécharger le Regional Flasher (Global/EU/IN) dans l'archive danielspringer.at",
            "Lancer Regional_Flasher.bat (fastboot puis fastbootd)",
            "Choisir la langue -> formater les données (obligatoire)",
        ],
        "risks": ["perte des données", "bon modèle requis (CPH2745/2747/2749/PLK110)"],
        "source_refs": ["droidwin.com/how-to-flash-fastboot-rom-on-oneplus-15",
                        "roms.danielspringer.at/index.php?dir=Oneplus+15"],
        "status": "verified",
        "contract": "Flash en fastboot+fastbootd restaure un firmware région de build complet.",
    },
    "unbrick_edl": {
        "aspect": "reparation",
        "steps": [
            "Installer drivers Qualcomm QDLoader (9008)",
            "Booter en EDL (Volume Up + câble USB)",
            "OPlus Flash Tool login (auth serveur) OU OPLUS EDL Tool / bkerler/edl",
            "Sélectionner le firmware OFP du modèle exact -> Start",
            "Attendre 100 % sans déconnecter -> débrancher -> allumer",
        ],
        "risks": ["nécessite autorisation EDL (serveurs OnePlus) — parfois indisponible",
                  "déconnexion pendant flash = hardbrick aggravé", "fichier EDL non public (auth required)"],
        "source_refs": ["droidwin.com/how-to-unbrick-oneplus-oppo-realme-via-oplus-edl-tool/",
                        "flashguidehub.com/oplus-edl-tool/",
                        "flashguidehub.com/bkerler-edl/",
                        "mgunlock.com/how-to-unbrick-oneplus-15-plk110-firmware"],
        "status": "verified",
        "contract": "EDL 9008 reconnu, flash OFP complet -> appareil restaurable (auth requise selon build).",
    },
    "convert_cn_to_global": {
        "aspect": "firmware",
        "steps": [
            "BL déverrouillé : flash du Regional Flasher Global en fastboot",
            "Ou EDL/Auth Flash via OPlus Flash Tool (appareils bloqués/brickés)",
            "Vérifier Google Play + OTA actives",
        ],
        "risks": ["anti-rollback ColorOS 16.0.3.501 (brick si rollback)", "notifications/réseau selon région"],
        "source_refs": ["droidwin.com/how-to-convert-oneplus-15-from-coloros-to-oxygenos/",
                        "ncunlock.com/product/oneplus-15-convert-global-rom-oxygenos-from-china-rom",
                        "androidcentral.com — mécanisme anti-rollback"],
        "status": "verified",
        "contract": "PLK110 passe sous OxygenOS global avec Google Play fonctionnel.",
    },
    "play_integrity_root": {
        "aspect": "amelioration",
        "steps": [
            "Activer Zygisk (Magisk) + DenyList sur les apps sensibles",
            "Modules : Shamiko + Play Integrity Fix (+ Tricky Store si STRONG requis)",
            "Vérifier avec une app Play Integrity Checker",
        ],
        "risks": ["aucun bypass permanent garanti", "re-tester après chaque OTA/maj d'app"],
        "source_refs": ["gizdev.com/pass-play-integrity-on-magisk",
                        "gizdev.com/pass-play-integrity-on-kernelsu/",
                        "droidrooter.com/blog/oneplus-root-guide-2026"],
        "status": "verified",
        "contract": "BASIC/DEVICE passent après config ; STRONG aléatoire (Tricky Store).",
    },
    "ota_apres_root": {
        "aspect": "firmware",
        "steps": [
            "Chemin A : flash manuel du nouveau init_boot patché (recommandé)",
            "Chemin B : init_boot stock -> OTA -> re-patcher -> re-flasher",
            "KernelSU : Install to Inactive Slot (After OTA)",
        ],
        "risks": ["OTA échoue sans re-patch", "slot inactif non rooté"],
        "source_refs": ["droidrooter.com/blog/oneplus-root-guide-2026",
                        "droidwin.com/how-to-install-ota-updates-on-rooted-device-via-kernelsu"],
        "status": "verified",
        "contract": "Le root survit à une OTA si le nouveau init_boot est re-patché.",
    },
    "custom_rom": {
        "aspect": "amelioration",
        "steps": [
            "Recovery OrangeFox (koaaN) installé en fastboot",
            "Kernel source OnePlus 15 PUBLIÉ (OnePlusOSS/android_kernel_oneplus_sm8850, branch sm8850_b_16.0.0_oneplus_15, Linux 6.11.0)",
            "Compiler un kernel custom (KernelSU/SUSFS) soi-même, ou attendre les ROMs AOSP stables",
            "Testbuilds : archive danielspringer.at (ex. Infinity-X) — statut experimental",
        ],
        "risks": ["ROMs AOSP stables pas encore confirmées (jeunes)", "caméra en retrait (avis)", "bêta"],
        "source_refs": ["xdaforums.com/t/oneplus-15-custom-roms.4767379",
                        "github.com/OnePlusOSS/android_kernel_oneplus_sm8850",
                        "github.com/OnePlusOSS/kernel_manifest/issues/124",
                        "github.com/koaaN/android_device_oneplus_infiniti-orangefox/releases"],
        "status": "in_progress",
        "contract": "Recovery fonctionnel ; kernel source publié ; ROMs AOSP stables non confirmées au 2026-08.",
    },
    "repair_batterie": {
        "aspect": "hardware",
        "steps": [
            "Éteindre, retirer le plateau SIM, chauffer le dos (~80°C) pour ramollir l'adhésif",
            "Succion + poche : décoller le verre arrière sans endommager le cadre",
            "Débrancher la nappe batterie de la carte mère (isolation électrique en premier)",
            "Soulever la cellule 7300 mAh (silicon-carbone, Glacier Battery) et retirer les adhésifs",
            "Poser la batterie d'origine neuve, reconnecter, tester (charge + diagnostic)",
            "Nettoyer, reposer le verre arrière avec adhésif neuf, presser 30 min",
        ],
        "risks": ["percement de la batterie = incendie (décharger <25 % avant)", "IP68/IP69K compromise après ouverture",
                  "ESD sur la carte mère", "pièce non d'origine = capacité/charge dégradées"],
        "source_refs": ["ifixit.com/Device/OnePlus_15",
                        "phonearena.com/news/oneplus-15-teardown",
                        "scribd.com/document/992192908/OnePlus-15-CPH2747-Repair-Manual-V1-1"],
        "status": "verified",
        "contract": "Cellule 7300 mAh remplacée par pièce d'origine, charge 120 W fonctionnelle, IP restaurée.",
    },
    "repair_ecran": {
        "aspect": "hardware",
        "steps": [
            "Décharger la batterie <25 %, chauffer le dos, retirer le verre arrière",
            "Débrancher batterie puis nappe écran (sous la cavité batterie)",
            "Déposer la carte mère (vis Phillips) + caméras + capteur d'empreinte",
            "Ensemble écran+cadre neuf (CPH2747) : transférer les composants en ordre inverse",
            "Tester AVANT de sceller : tactile, pixels morts, luminosité, empreinte",
            "Adhésif neuf + presser 30 min ; ne pas immerger après réparation",
        ],
        "risks": ["micro-déchirures des nappes lors du transfert", "perte d'étanchéité IP",
                  "capteur d'empreinte à recalibrer selon la version OS", "pièce hors CPH2747 incompatible"],
        "source_refs": ["phonerepair.co.uk/guides/oneplus-15-screen-replacement-expert-step-by-step-tutorial",
                        "ifixit.com/Device/OnePlus_15",
                        "dyiparts.com (écran CPH2745/CPH2747/PLK110)"],
        "status": "verified",
        "contract": "Écran AMOLED 6.78\" 165 Hz remplacé, tactile + empreinte fonctionnels après test pré-scellage.",
    },
    "degoogle_telemetrie": {
        "aspect": "amelioration",
        "steps": [
            "Inventorier les paquets télémétrie/OEM : pm list packages | grep -Ei 'telemetry|oem|diagnostic|analytics'",
            "Désactiver/supprimer les apps système espionnes (adb shell pm disable-user / pm uninstall --user 0)",
            "Couper la télémétrie OEM/OxygenOS : diagnostic, analytics, usage & diagnostic, photos cloud",
            "Option forte : GrapheneOS (Pixel uniquement — NON supporté OP15) ; sur OP15 : custom ROM deGOOGLisée + MicroG éventuel",
            "Vérifier les flux réseau sortants (AdGuard/NetGuard, firewall root) et DNS (blocage trackers)",
        ],
        "risks": ["app système indispensable désactivée par erreur (boucle)", "OTA peut réinstaller les apps",
                  "microG = compromis Google-libre mais moins stable", "apps bancaires peuvent refuser sans GMS"],
        "source_refs": ["grapheneos.org (modèle de réduction de télémétrie)",
                        "github.com/Universal-Debloater/all-in-one-script",
                        "github.com/AdguardTeam/AdGuardHome (DNS blocage)"],
        "status": "verified",
        "contract": "Suppression des paquets télémétrie/analytics système ; moins de données sortantes ; Play Integrity/apps peuvent casser sans GMS.",

        "note_validated_2026_08_15": "Sur CPH2747 build 400 : apps télémétrie OPlus (atlas, cosa, cota, dmp, gleanerservice, nas, aimemory, ocs, trafficmonitor, lfeh, nwestimate) déjà disabled (enabled=0). Aucun flux vers les serveurs identifiés par reverse (allawnos.com, fourier-newds01-sg, conn-service-eu, weather-api-eu). Private DNS AdGuard activé : settings put global private_dns_mode hostname ; settings put global private_dns_specifier dns.adguard-dns.com. Hosts système non modifié (partition read-only)."
    },
    "snapnpu_npu_qairt": {
        "aspect": "npu-llm",
        "steps": [
            "Qwen3-8B sur NPU QAIRT : force GENIEX_AIHUBVERSION=v0.60.0 avant GenieXSdk.init (le SDK 0.3.1 utilise v0.52.0 qui n'a pas le 8B)",
            "Nom correct du modele : ai-hub-models/Qwen3-8B (slug qwen3_8b, PAS Qwen3-8B-Instruct-2507)",
            "Chipset : SM8850 -> qualcomm-snapdragon-8-elite-gen5 (htp v81, soc_model 87) dans platform.json v0.60.0",
            "Asset : qwen3_8b-geniex_qairt-w4a16-qualcomm_snapdragon_8_elite_gen5.zip (QNN 2.45.0, 5 shards, ~5.1 Go)",
            "Résultat mesuré : decode 17.2 tok/s, prefill 287 tok/s, TTFT 90 ms (Qwen3-4B : 30.3 tok/s decode)",
            "Qwen3.5-9B : QAIRT ne supporte PAS les ops SSM/GatedDeltaNet (état KV-cache seul) ; backend hexagon llama.cpp deadlock après ~30 tokens (dspqueue FastRPC) -> 9B reste CPU 8.8 tok/s via SnapNPU",
            "SnapNPU (runtime maison) : fix 0x80000406 = skel libggml-htp-v81.so dans /data/local/tmp + ADSP_LIBRARY_PATH ; patch binaire libggml-hexagon.so @0xa3b0c/0xa44a4/0xa44b4 à re-pousser après pm install -r",
        ],
        "risks": ["téléchargement ~5 Go par modèle QAIRT", "deadlock backend hexagon sur 9B SSM",
                  "patch binaire hexagon perdu après réinstallation APK"],
        "source_refs": ["github.com/qualcomm/geniex-qairt", "github.com/qualcomm/ai-hub-models",
                        "github.com/ggml-org/llama.cpp/pull/26113", "aihub.qualcomm.com/models",
                        "docs/README.md:512 (AI Hub Models)"],
        "status": "verified",
        "contract": "Qwen3-8B w4a16 QAIRT tourne sur le NPU Hexagon du OnePlus 15 (SM8850) à 17.2 tok/s decode ; le 9B SSM n'est pas supporté par QAIRT ni stable sur le backend hexagon.",
    },
    "snapnpu_deadlock_0xc": {
        "aspect": "npu-llm",
        "steps": [
            "Symptôme : busy-loop dspqueue_cpu.c:2375 error 0xc wait_signal_locked(q, DSPQUEUE_SIGNAL_RESP_PACKET) en boucle, process 100% CPU, pas de génération",
            "0xc = AEE_EEXPIRED (AEEStdErr.h:60) = timeout 1s (DSPQUEUE_TIMEOUT 1000000us, NON réglable), retries infinis sans sleep",
            "CAUSE RACINE (reverse 16/08) : le skel /data/local/tmp/libggml-htp-v81.so du device est OBSOLETE (395244 octets, md5 686cc6c9) vs APK GenieX v0.4.0 (710636 octets, md5 1d4dbe09) -> host/skel incompatibles -> le DSP ne répond jamais",
            "FIX : pousser le BON skel (libggml-htp-v81.so de l'APK actuel, 710 Ko) vers /data/local/tmp + chmod 644 AVANT chaque bench (snapnpu_cycle.ps1 Do-Bench)",
            "Le skel v81 SUPPORTE ssm_conv(33), gated_delta_net(40), flash_attn_ext(24) ; ABSENTS : im2col(46), fusions QKV(6)/FFN(7)",
            "Env vars réglables : GGML_HEXAGON_OPPOLL=1 (poll non-bloquant), GGML_HEXAGON_OPBATCH (1024), GGML_HEXAGON_OPQUEUE (16) ; pas de GGML_HEXAGON_TIMEOUT",
            "Test discriminant : le host -patched (fixes unary+NULL) échoue pareil -> pas un crash d'op du host, c'est le skel",
            "Le modèle 9B charge OK (load rc=0), c'est le premier batch de génération qui timeout",
        ],
        "risks": ["skel obsolète sur device après pm install", "patch binaire hexagon perdu",
                  "OPFILTER/OPBATCH ne contournent pas le 0xc"],
        "source_refs": ["SYNTHESE_REVERSE_DEADLOCK_0XC.md", "AEEStdErr.h:60 (AEE_EEXPIRED)",
                        "github.com/ggml-org/llama.cpp ggml/src/ggml-hexagon"],
        "status": "in_progress",
        "contract": "Le deadlock 0xc vient du skel v81 obsolète sur le device (386 Ko) incompatible avec le host (APK 710 Ko) ; pousser le bon skel avant bench est le fix candidat à valider.",
    },
}

COMPONENTS = {
    "SoC": ["Snapdragon 8 Elite Gen 5", "3nm", "2x4.6GHz + 6x3.62GHz"],
    "GPU": ["Adreno 840"],
    "Ecran": ["6.78\" LTPO AMOLED", "165Hz", "1800 nits", "HDR10+", "Dolby Vision"],
    "Stockage": ["UFS 4.1", "jusqu'à 1 To", "16 Go RAM"],
    "Cameras": ["50 MP grand-angle OIS", "50 MP périscope 3.5x OIS", "50 MP ultra-large", "32 MP selfie"],
    "Batterie": ["7300 mAh", "silicon-carbone (Glacier Battery)", "charge 120 W filaire", "50 W sans fil"],
    "Connectique": ["USB-C 3.2", "Wi-Fi 6/7", "Bluetooth 6.0", "NFC", "IR", "dual SIM + eSIM"],
    "Durabilite": ["IP68/IP69K", "Gorilla Glass Victus 2", "cadre alu"],
}

RISKS = [
    "hardbrick", "bootloop", "effacement données", "annulation garantie",
    "Play Integrity", "apps bancaires", "anti-rollback", "TEE mismatch",
    "OTA échouée", "variante opérateur non déverrouillable",
]

# ============================================================================
# Catalogue des failles logicielles et matérielles connues / possibles.
# Axes d'interconnexion : partitions cibles, procédures qui les exploitent,
# outils impliqués, builds concernés, composants SoC affectés, risque associé.
#   status = "known"    : corroboré par des sources publiques indépendantes
#   status = "possible" : possible/communautaire, non confirmé sur appareil réel
# ============================================================================
VULNS = {
    # --- bootchain / logiciel OP15 (OxygenOS / ColorOS) --------------------
    "v_antrollback_efuse": {
        "famille": "bootchain_software", "label": "Anti-rollback / eFuse (rollback index)",
        "status": "known",
        "cibles": ["vbmeta", "abl", "efisp"],
        "vecteur": "Le firmware avance un index anti-rollback persisté (eFuse/flash) ; tout retour à une build plus ancienne est bloqué et peut hardbrick.",
        "impact": "Downgrade impossible ; brick définitif si flash d'une build antérieure à l'index.",
        "cves": [],
        "procedures": ["convert_cn_to_global", "flash_fastboot_rom"],
        "axes": ["firmware", "bootchain", "hardware"],
        "utilite": "Contrôle de version : interdit le downgrade, protège l'intégrité de la build flashée ; à contourner pour changer de région (ColorOS→OxygenOS) = conversion.",
        "determination": "Mécanisme documenté par OnePlus/Android Central (anti-rollback ColorOS 16.0.3.501) et l'ARB Checker. Aucun CVE public : ce n'est pas une vulnérabilité d'exploitation mais une contrainte matérielle.",
    },
    "v_gbl_abl": {
        "famille": "bootchain_software", "label": "GBL / ABL chainload (fake locked bootloader)",
        "status": "known",
        "cibles": ["efisp", "abl", "oplusreserve1"],
        "vecteur": "Faille de la chaîne de boot Qualcomm (ABL) : chaîner un BDS « superfastboot » depuis efisp pour maintenir un root sans drapeau de déverrouillage.",
        "impact": "Bootloader verrouillé mais rooté (fake locked) ; risque TEE mismatch / hardbrick.",
        "cves": [],
        "procedures": ["root_fake_locked"],
        "axes": ["bootchain", "root"],
        "utilite": "Root avec bootloader verrouillé (fake locked) : maintient Play Integrity/apps bancaires tout en gardant le root ; utile pour ceux qui refusent le drapeau unlocked.",
        "determination": "Confirmé par la communauté XDA (threads gbl-chainload + repo superturtlee/gbl_root_canoe). Non supporté officiellement ; Aucun CVE public (contournement de chaîne de boot).",
    },
    "v_edl_auth": {
        "famille": "bootchain_software", "label": "EDL / firehose : auth serveur (Qualcomm 9008)",
        "status": "known",
        "cibles": ["edl", "abl", "hyp"],
        "vecteur": "Le mode EDL 9008 exige une autorisation serveur OnePlus/Qualcomm ; les firehose de l'OP15 ne sont pas publics.",
        "impact": "Unbrick EDL bloqué sans auth serveur ; fichiers non publics.",
        "cves": [],
        "procedures": ["unbrick_edl"],
        "axes": ["reparation", "bootchain"],
        "utilite": "Réparation profonde (unbrick hardbrick) : accès direct au flash firehose ; requis pour restaurer un appareil brické non accessible en fastboot.",
        "determination": "Confirmé par les guides droidwin/flashguidehub (OPlus EDL Tool) et l'absence de firehose public pour CPH2747. L'auth serveur dépend des serveurs OnePlus. CVE-2018-13708 initialement cité était un faux positif (faille Ethereum) — retiré.",
    },
    "v_fastboot_unlock": {
        "famille": "bootchain_software", "label": "Fastboot unlock (pas de token, variante globale)",
        "status": "known",
        "cibles": ["abl"],
        "vecteur": "Sur la variante globale CPH2747, fastboot flashing unlock est disponible directement (sans In-Depth Test CN).",
        "impact": "Déverrouillage BL efface les données, annule la garantie, altère Play Integrity.",
        "cves": [],
        "procedures": ["bootloader_unlock_global", "bootloader_unlock_cn"],
        "axes": ["bootchain", "root"],
        "utilite": "Porte d'entrée de tout root/flash custom : nécessaire avant root Magisk/KernelSU/APatch, recovery, ROM.",
        "determination": "Confirmé par les guides communautaires (variante globale déverrouillable immédiatement) ; la variante CN exige l'app In-Depth Test.",
    },
    "v_vbmeta_avb": {
        "famille": "bootchain_software", "label": "vbmeta / AVB (bypass de vérification de boot)",
        "status": "known",
        "cibles": ["vbmeta", "dtbo", "boot_a", "boot_b"],
        "vecteur": "AVB peut être désactivé (fastboot --disable-verity/verification) une fois le BL déverrouillé ; le drapeau locked ne le rétablit pas.",
        "impact": "Boot non vérifié possible ; utile pour root/modif système.",
        "cves": [],
        "procedures": ["root_magisk", "root_kernelsu", "custom_rom"],
        "axes": ["bootchain", "root"],
        "utilite": "Root sans re-vérification AVB : facilite init_boot patché, modules, ROMs custom ; contourne l'échec de boot des partitions modifiées.",
        "determination": "Mécanisme AOSP standard (verification AVB) ; comportement confirmé par les workflows root Magisk/avbroot.",
    },
    "v_ota_rollback": {
        "famille": "bootchain_software", "label": "OTA / rollback protection",
        "status": "known",
        "cibles": ["system_a", "system_b"],
        "vecteur": "Les OTA vérifient la compatibilité de version ; un retour arrière via OTA est refusé (rollback index).",
        "impact": "Retour à un build antérieur refusé ; re-patch init_boot requis après OTA.",
        "cves": [],
        "procedures": ["ota_apres_root"],
        "axes": ["firmware", "bootchain"],
        "utilite": "Vérification de version OTA : impose de re-patcher init_boot après chaque mise à jour ; guide la stratégie de mise à jour d'un appareil rooté.",
        "determination": "Comportement standard Android A/B + contrainte anti-rollback OP15 ; confirmé par les guides OTA post-root.",
    },
    # --- SoC Qualcomm Snapdragon 8 Elite (SM8850) --------------------------
    "v_tee_trustzone": {
        "famille": "soc_qualcomm", "label": "TrustZone / TEE Qualcomm (SPS, sorter TA)",
        "status": "possible",
        "cibles": ["hyp", "tz", "abl"],
        "vecteur": "Historique de failles TEE Qualcomm (SPS/sorter TA, hyperviseur hyp). Surface d'attaque privilégiée, non confirmée sur SM8850.",
        "impact": "Si exploitable : compromission du monde sécurisé, bypass boot, accès aux données TEE.",
        "cves": ["CVE-2023-28547"],
        "procedures": [],
        "axes": ["soc", "bootchain"],
        "utilite": "Potentiel bypass de vérification TEE pour un root invisible (si exploit confirmé) ; surtout un risque de sécurité à corriger via patch.",
        "determination": "CVE-2023-28547 (CVSS 8.4, SPS sorter TA) attribué correctement à Qualcomm. Faiblesse confirmée sur d'autres SoC, NON confirmée exploitable sur SM8850 -> possible.",
    },
    "v_modem_baseband": {
        "famille": "soc_qualcomm", "label": "Modem / baseband",
        "status": "known",
        "cibles": ["modem"],
        "vecteur": "Failles baseband Qualcomm (UIM, LTE replay) exploitables à distance par la surface radio.",
        "impact": "Compromission à distance du modem, exfiltration, instabilité réseau, DoS.",
        "cves": ["CVE-2022-25694", "CVE-2021-30344"],
        "procedures": [],
        "axes": ["soc", "firmware"],
        "utilite": "Surface d'attaque radio : justifie le patch level à jour ; aucun usage constructif — risque à mitiger.",
        "determination": "CVE-2022-25694 (Modem UIM, CVSS 8.4) et CVE-2021-30344 (LTE replay, CVSS 7.5) sont Qualcomm. Le modem SM8850 partage la pile -> known (risque, pas d'exploitation locale).",
    },
    "v_microarch": {
        "famille": "soc_qualcomm", "label": "Micro-architectural (Adreno GPU / DSP / alloc mémoire)",
        "status": "possible",
        "cibles": ["dsp", "adsp"],
        "vecteur": "Historique de CVEs sur GPU Adreno (KGSL) et allocation mémoire (CVSS 8.4). Non confirmé exploitable sur SM8850.",
        "impact": "Élévation de privilèges kernel/userspace (LPE) selon le CVE.",
        "cves": ["CVE-2023-33106", "CVE-2023-33107", "CVE-2020-11261"],
        "procedures": ["root_kernelsu"],
        "axes": ["soc", "kernel"],
        "utilite": "Potentielle LPE utile si un exploit root parfait existe ; surtout un risque de sécurité à corriger via patch.",
        "determination": "CVE-2023-33106/33107 (KGSL Graphics, CVSS 8.4) et CVE-2020-11261 (Snapdragon alloc, CVSS 7.8) Qualcomm. Non confirmés exploitables sur SM8850 -> possible.",
    },
    # --- Android / système ---------------------------------------------------
    "v_android_patch": {
        "famille": "android", "label": "Android Security Bulletin / patch level",
        "status": "known",
        "cibles": ["system_a", "system_b", "vendor"],
        "vecteur": "Niveau de patch Android définit la surface de failles kernel/framework publiées chaque mois (SMR).",
        "impact": "Un patch level obsolète expose aux CVEs Android déjà publiées.",
        "cves": [],
        "procedures": ["ota_apres_root"],
        "axes": ["android", "kernel"],
        "utilite": "Référentiel de mise à jour : indique le niveau de sécurité minimal et guide la fréquence des OTA sur un appareil rooté.",
        "determination": "Mécanisme Android officiel (Security Bulletin mensuel) ; applicable à tout Android 16.",
    },
    "v_kernel_gki": {
        "famille": "android", "label": "Kernel GKI / framework LPE",
        "status": "known",
        "cibles": ["boot_a", "boot_b", "dtbo"],
        "vecteur": "CVEs kernel Android (GKI) et framework (PackageInstaller run-as) ; surface locale élevée (apps / adb).",
        "impact": "Élévation locale (LPE) ; root déjà acquis par d'autres moyens.",
        "cves": ["CVE-2024-0044", "CVE-2024-36971"],
        "procedures": ["root_magisk", "root_kernelsu"],
        "axes": ["kernel", "android"],
        "utilite": "Base technique du root via LPE (si exploit) ; surtout un risque à corriger via patch (run-as any app = exécution arbitraire).",
        "determination": "CVE-2024-0044 (PackageInstaller run-as, CVSS 6.7) et CVE-2024-36971 (kernel net dst, CVSS 7.8) confirmés Android/AOSP -> known.",
    },
    "v_playintegrity": {
        "famille": "android", "label": "Play Integrity / attestation",
        "status": "known",
        "cibles": ["vbmeta", "boot_a", "boot_b"],
        "vecteur": "La vérification Play Integrity dépend du drapeau de boot et du niveau de patch ; contournée partiellement (Tricky Store/Play Integrity Fix).",
        "impact": "BASIC/DEVICE restaurables ; STRONG non garanti.",
        "cves": [],
        "procedures": ["play_integrity_root"],
        "axes": ["android", "root"],
        "utilite": "Masquage du root pour les apps bancaires/Pay ; passer les vérifications BASIC/DEVICE après root.",
        "determination": "Comportement attestation Google documenté ; contournement partiel confirmé par les modules (Shamiko/PIF/Tricky Store).",
    },
    # --- Matériel ------------------------------------------------------------
    "v_fuses": {
        "famille": "hardware", "label": "eFuse / fuses de sécurité",
        "status": "known",
        "cibles": ["abl", "devcfg", "engineering_cdt"],
        "vecteur": "Fuses programmées une seule fois (garanties, boot, secure bits) ; non réversibles.",
        "impact": "Toute action qui fume une fuse est définitive (pas de retour).",
        "cves": [],
        "procedures": ["convert_cn_to_global"],
        "axes": ["hardware", "bootchain"],
        "utilite": "Verrou matériel définitif : avant d'agir, vérifier l'état des fuses (ARB checker) pour éviter un brick irréversible.",
        "determination": "Mécanisme hardware Qualcomm (fuses one-time) ; contrainte confirmée par l'anti-rollback. Aucun CVE public.",
    },
    "v_ufs": {
        "famille": "hardware", "label": "UFS / stockage (corruption, trim, brick)",
        "status": "possible",
        "cibles": ["super", "userdata"],
        "vecteur": "Erreurs de flash / corruption UFS pendant les opérations de partition ; répartition A/B.",
        "impact": "Données perdues, partition illisible, nécessite re-flash EDL.",
        "cves": [],
        "procedures": ["flash_fastboot_rom", "unbrick_edl"],
        "axes": ["hardware", "firmware"],
        "utilite": "Prudence de flash : sauvegarder avant toute opération de partition ; l'UFS A/B permet de conserver un slot sain.",
        "determination": "Risque opérationnel (corruption pendant flash) ; non lié à un CVE précis -> possible.",
    },
    "v_batterie": {
        "famille": "hardware", "label": "Batterie silicon-carbone (Glacier Battery)",
        "status": "known",
        "cibles": ["hardware"],
        "vecteur": "Cellule 7300 mAh silicon-carbone fragile : percement = incendie ; décharge <25 % avant ouverture.",
        "impact": "Risque physique (feu) si réparation non conforme ; pièces non d'origine dégradées.",
        "cves": [],
        "procedures": ["repair_batterie"],
        "axes": ["hardware", "reparation"],
        "utilite": "Règles de réparation : décharger <25 %, outils isolés, pièce d'origine pour préserver la charge 120 W.",
        "determination": "Caractéristique matérielle documentée (silicon-carbone) ; risque physique lors de la réparation.",
    },
    "v_ip68": {
        "famille": "hardware", "label": "Étanchéité IP68/IP69K",
        "status": "known",
        "cibles": ["hardware"],
        "vecteur": "Ouverture de l'appareil compromet l'étanchéité (adhésifs, joints).",
        "impact": "Perte de résistance à l'eau/poussière après réparation sans joint neuf.",
        "cves": [],
        "procedures": ["repair_batterie", "repair_ecran"],
        "axes": ["hardware", "reparation"],
        "utilite": "Protocole de réparation : adhésif neuf + pressage 30 min pour restaurer IP68/69K.",
        "determination": "Spécification constructeur (IP68/IP69K) ; compromission mécanique documentée.",
    },
}

VULN_FAMILIES = ["bootchain_software", "soc_qualcomm", "android", "hardware"]

# Motifs regex pour l'extracteur — ordre : spécifique d'abord.
PATTERNS = {
    "cve": r"\bCVE-\d{4}-\d{4,7}\b",
    "smr": r"\bSMR-(?:[A-Z]{3}-)?20\d{2}-\d{2}(?:-\d+)?\b",
    "vuln": r"\b(?:anti-rollback|anti rollback|rollback index|eFuse|TrustZone|TEE|baseband|modem|micro-architectur|GBL|ABL chainload|firehose|vbmeta|AVB|Play Integrity|patch level)\b",
    "tracker": r"\b(?:telemetry|télémétrie|analytics|diagnostic|tracker|espionnage|spyware|data collection|collecte de données)\b",
    "privacy": r"\b(?:GrapheneOS|MicroG|microG|deGooglis|deGooglis|unlock bootloader|privacy|vie privée|adb shell pm disable|pm uninstall)\b",
    "model": r"\b(?:CPH2745|CPH2747|CPH2749|PLK110)\b",
    "build": r"\b(?:CPH\d{4}|PLK\d{3})\w*(?:_\d+(?:\.\d+)*)+(?:\([A-Z]{2}\d*\))?" ,
    "os": r"\b(?:OxygenOS|ColorOS|Android\s+1[5-7])\b",
    "partition": r"\b(?:init_boot|boot_a|boot_b|vendor_boot|vbmeta|dtbo|efisp|abl|oplusreserve1|persist|recovery|super|system_a|system_b|vendor|modem|hyp|tz|dsp|adsp|devcfg|engineering_cdt|userdata)\b",
    "tool": r"\b(?:Magisk|KernelSU|APatch|SukiSU|OrangeFox|TWRP|payload-dumper|Oxygen\s+Updater|OPlus\s+Flash\s+Tool|MSM(?:\s+Download\s+Tool)?|OPLUS\s+EDL\s+Tool|bkerler/edl|Fastboot\s+Enhance\s+Tool|avbroot|DeepTestOP15|In-Depth\s+Test|Zygisk|Shamiko|Tricky\s+Store|Play\s+Integrity\s+Fix)\b",
    "procedure": r"\b(?:unlock|déverrouillage?|root|rooter|unbrick|brick|flash|OTA|convert(?:ir)?|relock|relocker)\b",
    "component": r"\b(?:Snapdragon|Adreno|AMOLED|LTPO|UFS\s*4\.1|Gorilla\s+Glass|7300\s*mAh|\d+\s*mAh)\b",
    "file_type": r"\b(?:payload\.bin|init_boot\.img|boot\.img|vbmeta\.img|\.efi|\.apk)\b",
    "risk": r"\b(?:hardbrick|bootloop|anti-rollback|Play\s+Integrity|garantie|warranty)\b",
}

FILE_ALIASES = {
    "init_boot.img": ["patched init_boot", "init_boot partition"],
    "efisp": ["efisp partition", "ABL_with_superfastboot.efi", "BDS.efi"],
    "oplusreserve1": ["oplus reserve1", "oplusreserve"],
}

ENTITY_TYPE_BY_PATTERN = {
    "model": "op15_model", "build": "op15_build", "os": "op15_os",
    "partition": "op15_partition", "tool": "op15_tool",
    "procedure": "op15_procedure", "component": "op15_component",
    "file_type": "op15_file", "risk": "op15_risk",
    "cve": "op15_cve", "smr": "op15_cve", "vuln": "op15_vuln",
    "tracker": "op15_privacy", "privacy": "op15_privacy",
}


def procedure_by_aspect(aspect: str) -> list[dict]:
    return [p for p in PROCEDURES.values() if p["aspect"] == aspect]


def vulns_by_family(famille: str) -> list[dict]:
    return [v for v in VULNS.values() if v["famille"] == famille]


def vulns_for_procedure(proc_name: str) -> list[dict]:
    return [v for v in VULNS.values() if proc_name in v.get("procedures", [])]


def catalog_summary() -> dict:
    return {
        "models": MODELS,
        "procedures": {name: {"aspect": p["aspect"], "status": p["status"]}
                       for name, p in PROCEDURES.items()},
        "components": list(COMPONENTS),
        "risks": RISKS,
        "vulns": {name: {"famille": v["famille"], "status": v["status"],
                         "cves": v["cves"], "axes": v["axes"]}
                  for name, v in VULNS.items()},
    }
