"""Shell tab-completion generation."""

from . import config as cfg_mod
from .effects import EFFECTS, BUILTIN_PRESETS
from .engines.kitten import VOICES as KITTEN_VOICES
from .engines.kokoro import VOICE_ALIASES as _KOKORO_ALIASES
from .engines.pocket import VOICES as POCKET_VOICES
from .engines.emojivoice import VOICES as EMOJIVOICE_VOICES

# Engine names for completion
ENGINES = ["kitten", "kokoro", "piper", "coqui", "pocket", "matcha", "emojivoice"]
# Bare names first (primary), canonical IDs after (long form, also accepted).
KOKORO_VOICES = list(_KOKORO_ALIASES.keys()) + list(_KOKORO_ALIASES.values())
SUBCOMMANDS = ["config", "daemon", "init", "install"]
CONFIG_ACTIONS = ["show", "get", "set"]
DAEMON_ACTIONS = ["start", "stop", "status", "start-all", "stop-all"]
INSTALL_FLAGS = ["--allow-sudo", "--reinstall", "--skip-selftest"]
CONFIG_PATHS = [
    "defaults.engine", "defaults.device", "defaults.speed", "defaults.play",
    "defaults.preprocessing",
    "engines.kitten.voice", "engines.kitten.model_size", "engines.kitten.device",
    "engines.kitten.daemon", "engines.kitten.preprocessing",
    "engines.kokoro.voice", "engines.kokoro.lang", "engines.kokoro.device",
    "engines.kokoro.daemon",
    "engines.piper.model", "engines.piper.device", "engines.piper.daemon",
    "engines.piper.noise_scale", "engines.piper.noise_w_scale",
    "engines.coqui.model", "engines.coqui.device", "engines.coqui.daemon",
    "engines.coqui.speaker", "engines.coqui.speaker_idx", "engines.coqui.language",
    "engines.coqui.speaker_wav", "engines.coqui.emotion",
    "engines.pocket.voice", "engines.pocket.device",
    "engines.matcha.model", "engines.matcha.device", "engines.matcha.daemon",
    "engines.matcha.steps", "engines.matcha.temperature",
    "engines.emojivoice.voice", "engines.emojivoice.device", "engines.emojivoice.daemon",
    "engines.emojivoice.steps", "engines.emojivoice.temperature",
    "presets.fast.kitten", "presets.fast.kokoro", "presets.fast.piper",
    "presets.fast.coqui", "presets.fast.pocket", "presets.fast.matcha",
    "presets.fast.emojivoice",
    "presets.balanced.kitten", "presets.balanced.kokoro", "presets.balanced.piper",
    "presets.balanced.coqui", "presets.balanced.pocket", "presets.balanced.matcha",
    "presets.balanced.emojivoice",
    "presets.quality.kitten", "presets.quality.kokoro", "presets.quality.piper",
    "presets.quality.coqui", "presets.quality.pocket", "presets.quality.matcha",
    "presets.quality.emojivoice",
]
EFFECT_NAMES = list(EFFECTS.keys()) + list(BUILTIN_PRESETS.keys())


def _alias_names() -> list:
    """Read configured alias names from disk. Best-effort — never raises."""
    try:
        cfg = cfg_mod.load()
        aliases = cfg.get("aliases") or {}
        # Skip aliases that shadow engine names (those are ignored at runtime).
        return [n for n in aliases.keys() if n not in ENGINES]
    except Exception:
        return []


def bash_completion() -> str:
    engines = " ".join(ENGINES)
    aliases = " ".join(_alias_names())
    kitten_voices = " ".join(KITTEN_VOICES)
    kokoro_voices = " ".join(KOKORO_VOICES)
    pocket_voices = " ".join(POCKET_VOICES)
    emojivoice_voices = " ".join(EMOJIVOICE_VOICES)
    subcommands = " ".join(SUBCOMMANDS)
    config_actions = " ".join(CONFIG_ACTIONS)
    daemon_actions = " ".join(DAEMON_ACTIONS)
    install_flags = " ".join(INSTALL_FLAGS)
    config_paths = " ".join(CONFIG_PATHS)
    effect_names = " ".join(EFFECT_NAMES)

    return f'''# marmalade-tts bash completion
# Add to .bashrc:  eval "$(marmalade-tts --completion bash)"

_marmalade_tts() {{
    local cur prev words cword
    _init_completion || return

    local engines="{engines}"
    local aliases="{aliases}"
    local subcommands="{subcommands}"
    local kitten_voices="{kitten_voices}"
    local kokoro_voices="{kokoro_voices}"
    local pocket_voices="{pocket_voices}"
    local emojivoice_voices="{emojivoice_voices}"
    local config_actions="{config_actions}"
    local daemon_actions="{daemon_actions}"
    local install_flags="{install_flags}"
    local config_paths="{config_paths}"
    local effect_names="{effect_names}"
    local flags="--out --play --no-play --speed --voice --lang --speaker \\
                 --speaker-wav --emotion \\
                 --fast --balanced --quality \\
                 --effect --no-effects --list-effects --list --list-aliases \\
                 --preprocessing --no-preprocessing \\
                 --list-rules --completion --quiet -q --json --print-path \\
                 --stdin --text -t --version --help -h"

    # First positional: engine, alias, or subcommand
    if [[ $cword -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$engines $aliases $subcommands" -- "$cur") )
        return
    fi

    # Config subcommand
    if [[ "${{words[1]}}" == "config" ]]; then
        if [[ $cword -eq 2 ]]; then
            COMPREPLY=( $(compgen -W "$config_actions" -- "$cur") )
        elif [[ $cword -eq 3 && ( "${{words[2]}}" == "set" || "${{words[2]}}" == "get" ) ]]; then
            COMPREPLY=( $(compgen -W "$config_paths" -- "$cur") )
        fi
        return
    fi

    # Daemon subcommand
    if [[ "${{words[1]}}" == "daemon" ]]; then
        if [[ $cword -eq 2 ]]; then
            COMPREPLY=( $(compgen -W "$daemon_actions" -- "$cur") )
        elif [[ "$prev" == "--engine" ]]; then
            COMPREPLY=( $(compgen -W "$engines" -- "$cur") )
        fi
        return
    fi

    # Install subcommand — engine names (repeatable) and install flags
    if [[ "${{words[1]}}" == "install" ]]; then
        COMPREPLY=( $(compgen -W "$engines $install_flags" -- "$cur") )
        return
    fi

    # Second positional after engine: voice name.
    # Only kitten/kokoro/pocket accept a positional voice — for those,
    # complete from the voice list. piper/coqui require --voice, so the
    # second positional there is text; offer flags instead.
    if [[ $cword -eq 2 ]]; then
        case "${{words[1]}}" in
            kitten)     COMPREPLY=( $(compgen -W "$kitten_voices" -- "$cur") ) ;;
            kokoro)     COMPREPLY=( $(compgen -W "$kokoro_voices" -- "$cur") ) ;;
            pocket)     COMPREPLY=( $(compgen -W "$pocket_voices" -- "$cur") ) ;;
            emojivoice) COMPREPLY=( $(compgen -W "$emojivoice_voices" -- "$cur") ) ;;
            *)          COMPREPLY=( $(compgen -W "$flags" -- "$cur") ) ;;
        esac
        return
    fi

    # --effect flag values: complete effect names
    if [[ "$prev" == "--effect" ]]; then
        COMPREPLY=( $(compgen -W "$effect_names" -- "$cur") )
        return
    fi

    # --voice flag values — engine-specific.
    # kitten/kokoro/pocket: complete from the voice list.
    # piper: voices are .onnx model files — complete file paths.
    # coqui: voices are tts_models/... specs — no practical completion.
    if [[ "$prev" == "--voice" ]]; then
        case "${{words[1]}}" in
            kitten)     COMPREPLY=( $(compgen -W "$kitten_voices" -- "$cur") ) ;;
            kokoro)     COMPREPLY=( $(compgen -W "$kokoro_voices" -- "$cur") ) ;;
            pocket)     COMPREPLY=( $(compgen -W "$pocket_voices" -- "$cur") ) ;;
            emojivoice) COMPREPLY=( $(compgen -W "$emojivoice_voices" -- "$cur") ) ;;
            piper)      _filedir onnx ;;
        esac
        return
    fi

    # --lang flag values
    if [[ "$prev" == "--lang" ]]; then
        COMPREPLY=( $(compgen -W "a b j z" -- "$cur") )
        return
    fi

    # File completion for --out and --speaker-wav (both take file paths)
    if [[ "$prev" == "--out" || "$prev" == "--speaker-wav" ]]; then
        _filedir
        return
    fi

    # Flags anywhere
    if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "$flags" -- "$cur") )
        return
    fi
}}

complete -F _marmalade_tts marmalade-tts
'''


def zsh_completion() -> str:
    engines = " ".join(ENGINES)
    aliases = " ".join(_alias_names())
    kitten_voices = " ".join(KITTEN_VOICES)
    kokoro_voices = " ".join(KOKORO_VOICES)
    pocket_voices = " ".join(POCKET_VOICES)
    emojivoice_voices = " ".join(EMOJIVOICE_VOICES)
    effect_names = " ".join(EFFECT_NAMES)

    return f'''#compdef marmalade-tts
# marmalade-tts zsh completion
# Add to .zshrc:  eval "$(marmalade-tts --completion zsh)"

_marmalade-tts() {{
    local curcontext="$curcontext" state line
    local -a engines=({engines})
    local -a aliases=({aliases})
    local -a subcommands=(config daemon init install)
    local -a kitten_voices=({kitten_voices})
    local -a kokoro_voices=({kokoro_voices})
    local -a pocket_voices=({pocket_voices})
    local -a emojivoice_voices=({emojivoice_voices})
    local -a effect_names=({effect_names})

    # Engine-aware voice completion, shared by the positional voice slot
    # and the --voice flag. Reads $words[2] (the engine) to decide.
    _marmalade_voices() {{
        case "${{words[2]}}" in
            kitten)     _values 'kitten voice' $kitten_voices ;;
            kokoro)     _values 'kokoro voice' $kokoro_voices ;;
            pocket)     _values 'pocket voice' $pocket_voices ;;
            emojivoice) _values 'emojivoice speaker' $emojivoice_voices ;;
            piper)      _files -g '*.onnx' ;;
            *) ;;  # coqui / matcha: model specs — no practical completion
        esac
    }}

    _arguments -C \\
        '1:engine, alias or subcommand:->engine' \\
        '2:voice or text:->arg2' \\
        '*::text:' \\
        '--out[Output WAV file]:file:_files' \\
        '--play[Force playback]' \\
        '--no-play[Skip playback]' \\
        '--quiet[Suppress non-audio output]' \\
        '--json[Emit JSON status to stdout]' \\
        '--print-path[Print output path]' \\
        '--stdin[Read text from stdin]' \\
        '(-t --text)'{{-t,--text}}'[Text to synthesize]:text:' \\
        '--speed[Speech speed]:speed:' \\
        '--voice[Voice/model override]:voice:->voiceflag' \\
        '--lang[Language code]:lang:(a b j z)' \\
        '--speaker[Speaker ID or name]:id:' \\
        '--speaker-wav[Reference WAV for voice cloning (Coqui XTTS)]:file:_files' \\
        '--emotion[Emotion label (Coqui emotion-aware models)]:emotion:' \\
        '--fast[Fast preset]' \\
        '--balanced[Balanced preset]' \\
        '--quality[Quality preset]' \\
        '*--effect[Audio effect]:effect:(($effect_names))' \\
        '--no-effects[Skip all effects, including config defaults]' \\
        '--list-effects[List available audio effects and presets]' \\
        '--list-aliases[List configured voice aliases / personas]' \\
        '--list[List voices]' \\
        '--preprocessing[Enable text preprocessing]' \\
        '--no-preprocessing[Disable text preprocessing]' \\
        '--list-rules[List preprocessing rules]' \\
        '--version[Print version]' \\
        '--completion[Generate completion]:shell:(bash zsh)'

    case $state in
        engine)
            _values 'engine, alias or subcommand' $engines $aliases $subcommands
            ;;
        arg2)
            # Second positional: a voice for kitten/kokoro/pocket/piper,
            # otherwise free text.
            _marmalade_voices
            ;;
        voiceflag)
            _marmalade_voices
            ;;
    esac
}}

_marmalade-tts "$@"
'''
