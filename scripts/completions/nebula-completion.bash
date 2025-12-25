#!/bin/bash
# Bash completion script for NebulaCompute CLI tools
#
# Installation:
#   source /path/to/nebula-completion.bash
# Or add to ~/.bashrc:
#   source /path/to/nebula-completion.bash

_nebula_get_workers() {
    dc-worker list 2>/dev/null | grep -oP '^\w+' | head -20
}

_nebula_get_jobs() {
    dc-submit list 2>/dev/null | grep -oP '^[a-f0-9-]+' | head -20
}

# dc-master completion
_dc_master() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="start stop status config metrics workers jobs health version --help"
    subcommands_start="--host --port --workers --config --log-level --daemon"
    subcommands_config="show set get reset"

    case "${prev}" in
        dc-master)
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            return 0
            ;;
        start)
            COMPREPLY=( $(compgen -W "${subcommands_start}" -- "${cur}") )
            return 0
            ;;
        config)
            COMPREPLY=( $(compgen -W "${subcommands_config}" -- "${cur}") )
            return 0
            ;;
        --host)
            COMPREPLY=( $(compgen -W "localhost 0.0.0.0 127.0.0.1" -- "${cur}") )
            return 0
            ;;
        --port)
            COMPREPLY=( $(compgen -W "8000 8080 9000" -- "${cur}") )
            return 0
            ;;
        --log-level)
            COMPREPLY=( $(compgen -W "DEBUG INFO WARNING ERROR CRITICAL" -- "${cur}") )
            return 0
            ;;
        --config)
            COMPREPLY=( $(compgen -f -X '!*.yaml' -- "${cur}") $(compgen -f -X '!*.yml' -- "${cur}") )
            return 0
            ;;
        *)
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            return 0
            ;;
    esac
}

# dc-worker completion
_dc_worker() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="start stop status list register deregister drain activate metrics logs --help"
    subcommands_start="--master --name --tags --cpus --memory --gpus --config"
    subcommands_list="--status --format --limit"

    case "${prev}" in
        dc-worker)
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            return 0
            ;;
        start)
            COMPREPLY=( $(compgen -W "${subcommands_start}" -- "${cur}") )
            return 0
            ;;
        list)
            COMPREPLY=( $(compgen -W "${subcommands_list}" -- "${cur}") )
            return 0
            ;;
        drain|activate|deregister|logs|metrics)
            local workers=$(_nebula_get_workers)
            COMPREPLY=( $(compgen -W "${workers}" -- "${cur}") )
            return 0
            ;;
        --status)
            COMPREPLY=( $(compgen -W "online offline busy draining all" -- "${cur}") )
            return 0
            ;;
        --format)
            COMPREPLY=( $(compgen -W "table json yaml" -- "${cur}") )
            return 0
            ;;
        --master)
            COMPREPLY=( $(compgen -W "localhost:8000 localhost:9000" -- "${cur}") )
            return 0
            ;;
        *)
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            return 0
            ;;
    esac
}

# dc-submit completion
_dc_submit() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="run list status cancel retry logs result wait --help"
    subcommands_run="--name --priority --cpus --memory --gpus --timeout --depends-on --config"
    subcommands_list="--status --limit --format --user"

    case "${prev}" in
        dc-submit)
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            return 0
            ;;
        run)
            COMPREPLY=( $(compgen -W "${subcommands_run}" -- "${cur}") $(compgen -f -- "${cur}") )
            return 0
            ;;
        list)
            COMPREPLY=( $(compgen -W "${subcommands_list}" -- "${cur}") )
            return 0
            ;;
        status|cancel|retry|logs|result|wait)
            local jobs=$(_nebula_get_jobs)
            COMPREPLY=( $(compgen -W "${jobs}" -- "${cur}") )
            return 0
            ;;
        --status)
            COMPREPLY=( $(compgen -W "pending running completed failed cancelled all" -- "${cur}") )
            return 0
            ;;
        --priority)
            COMPREPLY=( $(compgen -W "low normal high critical" -- "${cur}") )
            return 0
            ;;
        --format)
            COMPREPLY=( $(compgen -W "table json yaml" -- "${cur}") )
            return 0
            ;;
        --depends-on)
            local jobs=$(_nebula_get_jobs)
            COMPREPLY=( $(compgen -W "${jobs}" -- "${cur}") )
            return 0
            ;;
        *)
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            return 0
            ;;
    esac
}

# dc-ai completion
_dc_ai() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="chat complete embed models status config --help"
    subcommands_chat="--model --temperature --max-tokens --system --stream"
    subcommands_models="list info pull remove"

    case "${prev}" in
        dc-ai)
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            return 0
            ;;
        chat|complete)
            COMPREPLY=( $(compgen -W "${subcommands_chat}" -- "${cur}") )
            return 0
            ;;
        models)
            COMPREPLY=( $(compgen -W "${subcommands_models}" -- "${cur}") )
            return 0
            ;;
        --model)
            COMPREPLY=( $(compgen -W "llama2 mistral codellama phi gemma" -- "${cur}") )
            return 0
            ;;
        --temperature)
            COMPREPLY=( $(compgen -W "0.0 0.3 0.5 0.7 1.0" -- "${cur}") )
            return 0
            ;;
        *)
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            return 0
            ;;
    esac
}

# dc-web completion
_dc_web() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="start stop status --host --port --workers --reload --help"

    case "${prev}" in
        --host)
            COMPREPLY=( $(compgen -W "localhost 0.0.0.0 127.0.0.1" -- "${cur}") )
            return 0
            ;;
        --port)
            COMPREPLY=( $(compgen -W "8000 8080 3000 5000" -- "${cur}") )
            return 0
            ;;
        *)
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            return 0
            ;;
    esac
}

# dc-mesh completion
_dc_mesh() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="start stop join leave peers status discover --help"
    subcommands_start="--port --bootstrap --name --config"

    case "${prev}" in
        dc-mesh)
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            return 0
            ;;
        start)
            COMPREPLY=( $(compgen -W "${subcommands_start}" -- "${cur}") )
            return 0
            ;;
        *)
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            return 0
            ;;
    esac
}

# dc-workflow completion
_dc_workflow() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="run list status cancel pause resume logs visualize --help"
    subcommands_run="--file --name --params --dry-run"

    case "${prev}" in
        dc-workflow)
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            return 0
            ;;
        run)
            COMPREPLY=( $(compgen -W "${subcommands_run}" -- "${cur}") $(compgen -f -X '!*.yaml' -- "${cur}") )
            return 0
            ;;
        --file)
            COMPREPLY=( $(compgen -f -X '!*.yaml' -- "${cur}") $(compgen -f -X '!*.yml' -- "${cur}") )
            return 0
            ;;
        *)
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            return 0
            ;;
    esac
}

# dc-secrets completion
_dc_secrets() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="set get list delete rotate --help"

    case "${prev}" in
        dc-secrets)
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            return 0
            ;;
        *)
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            return 0
            ;;
    esac
}

# dc-inference completion
_dc_inference() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="start stop status serve predict batch --help"
    subcommands_start="--model --port --workers --gpu --batch-size"

    case "${prev}" in
        dc-inference)
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            return 0
            ;;
        start|serve)
            COMPREPLY=( $(compgen -W "${subcommands_start}" -- "${cur}") )
            return 0
            ;;
        *)
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            return 0
            ;;
    esac
}

# Register completions
complete -F _dc_master dc-master
complete -F _dc_worker dc-worker
complete -F _dc_submit dc-submit
complete -F _dc_ai dc-ai
complete -F _dc_web dc-web
complete -F _dc_mesh dc-mesh
complete -F _dc_workflow dc-workflow
complete -F _dc_secrets dc-secrets
complete -F _dc_inference dc-inference

echo "NebulaCompute CLI completions loaded"
