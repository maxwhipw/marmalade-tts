"""Shell tab-completion generation."""

from .effects import EFFECTS, BUILTIN_PRESETS

# Engine names and known voices for completion
ENGINES = ["kitten", "kokoro", "piper", "coqui", "pocket"]
KITTEN_VOICES = ["Bella", "Jasper", "Luna", "Bruno", "Rosie", "Hugo", "Kiki", "Leo"]
KOKORO_VOICES = [
    "af_heart", "af_bella", "af_nicole", "am_adam", "am_michael",
    "bf_emma", "bf_isabella", "bm_george", "bm_lewis",
    "jf_alpha", "jf_gongitsune", "jm_kumo", "zf_xiaobei", "zm_yunjian",
]
POCKET_VOICES = ["alba", "marius", "javert", "jean", "fantine", "cosette", "eponine", "azelma"]
SUBCOMMANDS = ["config", "daemon", "init"]
CONFIG_ACTIONS = ["show", "get", "set"]
DAEMON_ACTIONS = ["start", "stop", "status", "start-all", "stop-all"]
CONFIG_PATHS = [
    "defaults.engine", "defaults.device", "defaults.speed", "defaults.play",
    "defaults.preprocessing",
    "engines.kitten.voice", "engines.kitten.model_size", "engines.kitten.device",
    "engines.kitten.daemon", "engines.kitten.preprocessing",
    "engines.kokoro.voice", "engines.kokoro.lang", "engines.kokoro.device",
    "engines.kokoro.daemon",
    "engines.piper.model", "engines.piper.device", "engines.piper.daemon",
    "engines.coqui.model", "engines.coqui.device", "engines.coqui.daemon",
    "engines.pocket.voice", "engines.pocket.device",
    "presets.fast.kitten", "presets.fast.kokoro", "presets.fast.piper",
    "presets.fast.coqui", "presets.fast.pocket",
    "presets.balanced.kitten", "presets.balanced.kokoro", "presets.balanced.piper",
    "presets.balanced.coqui", "presets.balanced.pocket",
    "presets.quality.kitten", "presets.quality.kokoro", "presets.quality.piper",
    "presets.quality.coqui", "presets.quality.pocket",
]
EFFECT_NAMES = list(EFFECTS.keys()) + list(BUILTIN_PRESETS.keys())


def bash_completion() -> str:
    engines = " ".join(ENGINES)
    kitten_voices = " ".join(KITTEN_VOICES)
    kokoro_voices = " ".join(KOKORO_VOICES)
    pocket_voices = " ".join(POCKET_VOICES)
    subcommands = " ".join(SUBCOMMANDS)
    config_actions = " ".join(CONFIG_ACTIONS)
    daemon_actions = " ".join(DAEMON_ACTIONS)
    config_paths = " ".join(CONFIG_PATHS)
    effect_names = " ".join(EFFECT_NAMES)

    return f'''# marmalade-tts bash completion
# Add to .bashrc:  eval "$(marmalade-tts --completion bash)"

_marmalade_tts() {{
    local cur prev words cword
    _init_completion || return

    local engines="{engines}"
    local subcommands="{subcommands}"
    local kitten_voices="{kitten_voices}"
    local kokoro_voices="{kokoro_voices}"
    local pocket_voices="{pocket_voices}"
    local config_actions="{config_actions}"
    local daemon_actions="{daemon_actions}"
    local config_paths="{config_paths}"
    local effect_names="{effect_names}"
    local flags="--out --play --no-play --speed --voice --lang --speaker \\
                 --fast --balanced --quality \\
                 --effect --list-effects --list --preprocessing --no-preprocessing \\
                 --list-rules --completion --quiet --json --print-path \\
                 --stdin --text -t --version"

    # First positional: engine or subcommand
    if [[ $cword -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$engines $subcommands" -- "$cur") )
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

    # Second positional after engine: voice name
    if [[ $cword -eq 2 ]]; then
        case "${{words[1]}}" in
            kitten) COMPREPLY=( $(compgen -W "$kitten_voices" -- "$cur") ) ;;
            kokoro) COMPREPLY=( $(compgen -W "$kokoro_voices" -- "$cur") ) ;;
            pocket) COMPREPLY=( $(compgen -W "$pocket_voices" -- "$cur") ) ;;
            *)      COMPREPLY=( $(compgen -W "$flags" -- "$cur") ) ;;
        esac
        return
    fi

    # --effect flag values: complete effect names
    if [[ "$prev" == "--effect" ]]; then
        COMPREPLY=( $(compgen -W "$effect_names" -- "$cur") )
        return
    fi

    # --voice flag values
    if [[ "$prev" == "--voice" ]]; then
        case "${{words[1]}}" in
            kitten) COMPREPLY=( $(compgen -W "$kitten_voices" -- "$cur") ) ;;
            kokoro) COMPREPLY=( $(compgen -W "$kokoro_voices" -- "$cur") ) ;;
            pocket) COMPREPLY=( $(compgen -W "$pocket_voices" -- "$cur") ) ;;
        esac
        return
    fi

    # --lang flag values
    if [[ "$prev" == "--lang" ]]; then
        COMPREPLY=( $(compgen -W "a b h e f i p j z" -- "$cur") )
        return
    fi

    # File completion for --out
    if [[ "$prev" == "--out" ]]; then
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
    kitten_voices = " ".join(KITTEN_VOICES)
    kokoro_voices = " ".join(KOKORO_VOICES)
    pocket_voices = " ".join(POCKET_VOICES)
    effect_names = " ".join(EFFECT_NAMES)

    return f'''#compdef marmalade-tts
# marmalade-tts zsh completion
# Add to .zshrc:  eval "$(marmalade-tts --completion zsh)"

_marmalade-tts() {{
    local -a engines=({engines})
    local -a subcommands=(config daemon init)
    local -a kitten_voices=({kitten_voices})
    local -a kokoro_voices=({kokoro_voices})
    local -a pocket_voices=({pocket_voices})
    local -a effect_names=({effect_names})
    local -a daemon_actions=(start stop status start-all stop-all)

    _arguments \\
        '1:engine_or_subcmd:((${{engines}} ${{subcommands}}))' \\
        '2:voice_or_text:' \\
        '*:text:' \\
        '--out[Output WAV file]:file:_files' \\
        '--play[Force playback]' \\
        '--no-play[Skip playback]' \\
        '--quiet[Suppress non-audio output]' \\
        '--json[Emit JSON status to stdout]' \\
        '--print-path[Print output path]' \\
        '--stdin[Read text from stdin]' \\
        '(-t --text)'{{-t,--text}}'[Text to synthesize]:text:' \\
        '--speed[Speech speed]:speed:' \\
        '--voice[Voice name]:voice:((${{kitten_voices}} ${{kokoro_voices}} ${{pocket_voices}}))' \\
        '--lang[Language code]:lang:(a b h e f i p j z)' \\
        '--speaker[Speaker ID]:id:' \\
        '--fast[Fast preset]' \\
        '--balanced[Balanced preset]' \\
        '--quality[Quality preset]' \\
        '*--effect[Audio effect]:effect:((${{effect_names}}))' \\
        '--list-effects[List available audio effects and presets]' \\
        '--list[List voices]' \\
        '--preprocessing[Enable text preprocessing]' \\
        '--no-preprocessing[Disable text preprocessing]' \\
        '--list-rules[List preprocessing rules]' \\
        '--version[Print version]' \\
        '--completion[Generate completion]:shell:(bash zsh)'
}}

_marmalade-tts "$@"
'''
