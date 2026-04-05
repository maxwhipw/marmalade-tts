"""Shell tab-completion generation."""

# Engine names and known voices for completion
ENGINES = ["kitten", "kokoro", "piper", "coqui"]
KITTEN_VOICES = ["Bella", "Jasper", "Luna", "Bruno", "Rosie", "Hugo", "Kiki", "Leo"]
KOKORO_VOICES = [
    "af_heart", "af_bella", "af_nicole", "am_adam", "am_michael",
    "bf_emma", "bf_isabella", "bm_george", "bm_lewis",
    "jf_alpha", "jf_gongitsune", "jm_kumo", "zf_xiaobei", "zm_yunjian",
]
SUBCOMMANDS = ["config", "daemon"]
CONFIG_ACTIONS = ["show", "get", "set"]
DAEMON_ACTIONS = ["start", "stop", "status"]
CONFIG_PATHS = [
    "defaults.engine", "defaults.device", "defaults.speed", "defaults.play",
    "engines.kitten.voice", "engines.kitten.model_size", "engines.kitten.device", "engines.kitten.daemon",
    "engines.kokoro.voice", "engines.kokoro.lang", "engines.kokoro.device",
    "engines.piper.model", "engines.piper.device",
    "engines.coqui.model", "engines.coqui.device",
    "presets.fast.kitten", "presets.fast.kokoro",
    "presets.balanced.kitten", "presets.balanced.kokoro",
    "presets.quality.kitten", "presets.quality.kokoro",
]


def bash_completion() -> str:
    engines = " ".join(ENGINES)
    kitten_voices = " ".join(KITTEN_VOICES)
    kokoro_voices = " ".join(KOKORO_VOICES)
    subcommands = " ".join(SUBCOMMANDS)
    config_actions = " ".join(CONFIG_ACTIONS)
    daemon_actions = " ".join(DAEMON_ACTIONS)
    config_paths = " ".join(CONFIG_PATHS)

    return f'''# marmalade-tts bash completion
# Add to .bashrc:  eval "$(marmalade-tts --completion bash)"

_marmalade_tts() {{
    local cur prev words cword
    _init_completion || return

    local engines="{engines}"
    local subcommands="{subcommands}"
    local kitten_voices="{kitten_voices}"
    local kokoro_voices="{kokoro_voices}"
    local config_actions="{config_actions}"
    local daemon_actions="{daemon_actions}"
    local config_paths="{config_paths}"
    local flags="--out --play --speed --voice --lang --speaker --fast --balanced --quality --list --completion"

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
        fi
        return
    fi

    # Second positional after engine: voice name
    if [[ $cword -eq 2 ]]; then
        case "${{words[1]}}" in
            kitten) COMPREPLY=( $(compgen -W "$kitten_voices" -- "$cur") ) ;;
            kokoro) COMPREPLY=( $(compgen -W "$kokoro_voices" -- "$cur") ) ;;
            *)      COMPREPLY=( $(compgen -W "$flags" -- "$cur") ) ;;
        esac
        return
    fi

    # Flags anywhere
    if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "$flags" -- "$cur") )
        return
    fi

    # --voice flag values
    if [[ "$prev" == "--voice" ]]; then
        case "${{words[1]}}" in
            kitten) COMPREPLY=( $(compgen -W "$kitten_voices" -- "$cur") ) ;;
            kokoro) COMPREPLY=( $(compgen -W "$kokoro_voices" -- "$cur") ) ;;
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
}}

complete -F _marmalade_tts marmalade-tts
'''


def zsh_completion() -> str:
    engines = " ".join(ENGINES)
    kitten_voices = " ".join(KITTEN_VOICES)
    kokoro_voices = " ".join(KOKORO_VOICES)

    return f'''#compdef marmalade-tts
# marmalade-tts zsh completion
# Add to .zshrc:  eval "$(marmalade-tts --completion zsh)"

_marmalade-tts() {{
    local -a engines=({engines})
    local -a subcommands=(config daemon)
    local -a kitten_voices=({kitten_voices})
    local -a kokoro_voices=({kokoro_voices})

    _arguments \\
        '1:engine:((${{engines}} ${{subcommands}}))' \\
        '2:voice_or_text:' \\
        '*:text:' \\
        '--out[Output WAV file]:file:_files' \\
        '--play[Force playback]' \\
        '--speed[Speech speed]:speed:' \\
        '--voice[Voice name]:voice:((${{kitten_voices}} ${{kokoro_voices}}))' \\
        '--lang[Language code]:lang:(a b h e f i p j z)' \\
        '--speaker[Speaker ID]:id:' \\
        '--fast[Fast preset]' \\
        '--balanced[Balanced preset]' \\
        '--quality[Quality preset]' \\
        '--list[List voices]' \\
        '--completion[Generate completion]:shell:(bash zsh)'
}}

_marmalade-tts "$@"
'''
