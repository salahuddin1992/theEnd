#compdef dc-master dc-worker dc-submit dc-ai dc-web dc-mesh dc-workflow dc-secrets dc-inference

# Zsh completion script for NebulaCompute CLI tools
#
# Installation:
#   1. Copy to your fpath: cp nebula-completion.zsh ~/.zsh/completions/_nebula
#   2. Add to fpath in ~/.zshrc: fpath=(~/.zsh/completions $fpath)
#   3. Enable completions: autoload -Uz compinit && compinit

# Helper functions
_nebula_workers() {
    local workers
    workers=(${(f)"$(dc-worker list 2>/dev/null | grep -oP '^\w+' | head -20)"})
    _describe 'workers' workers
}

_nebula_jobs() {
    local jobs
    jobs=(${(f)"$(dc-submit list 2>/dev/null | grep -oP '^[a-f0-9-]+' | head -20)"})
    _describe 'jobs' jobs
}

# dc-master completion
_dc-master() {
    local -a commands
    commands=(
        'start:Start the master server'
        'stop:Stop the master server'
        'status:Show master status'
        'config:Manage configuration'
        'metrics:Show metrics'
        'workers:List connected workers'
        'jobs:List all jobs'
        'health:Health check'
        'version:Show version'
    )

    local -a start_opts
    start_opts=(
        '--host[Host to bind to]:host:(localhost 0.0.0.0 127.0.0.1)'
        '--port[Port to listen on]:port:(8000 8080 9000)'
        '--workers[Number of worker processes]:workers:'
        '--config[Configuration file]:config:_files -g "*.yaml *.yml"'
        '--log-level[Logging level]:level:(DEBUG INFO WARNING ERROR CRITICAL)'
        '--daemon[Run as daemon]'
    )

    local -a config_commands
    config_commands=(
        'show:Show current configuration'
        'set:Set configuration value'
        'get:Get configuration value'
        'reset:Reset to defaults'
    )

    _arguments -C \
        '1:command:->command' \
        '*::arg:->args'

    case $state in
        command)
            _describe 'command' commands
            ;;
        args)
            case $words[1] in
                start)
                    _arguments $start_opts
                    ;;
                config)
                    _describe 'config command' config_commands
                    ;;
            esac
            ;;
    esac
}

# dc-worker completion
_dc-worker() {
    local -a commands
    commands=(
        'start:Start worker agent'
        'stop:Stop worker agent'
        'status:Show worker status'
        'list:List all workers'
        'register:Register worker'
        'deregister:Deregister worker'
        'drain:Drain worker for maintenance'
        'activate:Activate drained worker'
        'metrics:Show worker metrics'
        'logs:Show worker logs'
    )

    local -a start_opts
    start_opts=(
        '--master[Master server address]:master:(localhost:8000 localhost:9000)'
        '--name[Worker name]:name:'
        '--tags[Worker tags]:tags:'
        '--cpus[CPU cores]:cpus:'
        '--memory[Memory in MB]:memory:'
        '--gpus[GPU count]:gpus:'
        '--config[Configuration file]:config:_files -g "*.yaml *.yml"'
    )

    local -a list_opts
    list_opts=(
        '--status[Filter by status]:status:(online offline busy draining all)'
        '--format[Output format]:format:(table json yaml)'
        '--limit[Limit results]:limit:'
    )

    _arguments -C \
        '1:command:->command' \
        '*::arg:->args'

    case $state in
        command)
            _describe 'command' commands
            ;;
        args)
            case $words[1] in
                start)
                    _arguments $start_opts
                    ;;
                list)
                    _arguments $list_opts
                    ;;
                drain|activate|deregister|logs|metrics)
                    _nebula_workers
                    ;;
            esac
            ;;
    esac
}

# dc-submit completion
_dc-submit() {
    local -a commands
    commands=(
        'run:Submit a new job'
        'list:List jobs'
        'status:Get job status'
        'cancel:Cancel a job'
        'retry:Retry a failed job'
        'logs:View job logs'
        'result:Get job result'
        'wait:Wait for job completion'
    )

    local -a run_opts
    run_opts=(
        '--name[Job name]:name:'
        '--priority[Job priority]:priority:(low normal high critical)'
        '--cpus[CPU cores]:cpus:'
        '--memory[Memory in MB]:memory:'
        '--gpus[GPU count]:gpus:'
        '--timeout[Timeout in seconds]:timeout:'
        '--depends-on[Job dependencies]:depends:'
        '--config[Configuration file]:config:_files -g "*.yaml *.yml"'
        '*:file:_files'
    )

    local -a list_opts
    list_opts=(
        '--status[Filter by status]:status:(pending running completed failed cancelled all)'
        '--format[Output format]:format:(table json yaml)'
        '--limit[Limit results]:limit:'
        '--user[Filter by user]:user:'
    )

    _arguments -C \
        '1:command:->command' \
        '*::arg:->args'

    case $state in
        command)
            _describe 'command' commands
            ;;
        args)
            case $words[1] in
                run)
                    _arguments $run_opts
                    ;;
                list)
                    _arguments $list_opts
                    ;;
                status|cancel|retry|logs|result|wait)
                    _nebula_jobs
                    ;;
            esac
            ;;
    esac
}

# dc-ai completion
_dc-ai() {
    local -a commands
    commands=(
        'chat:Start interactive chat'
        'complete:Text completion'
        'embed:Generate embeddings'
        'models:Manage models'
        'status:Show AI service status'
        'config:Configure AI settings'
    )

    local -a chat_opts
    chat_opts=(
        '--model[Model to use]:model:(llama2 mistral codellama phi gemma)'
        '--temperature[Temperature]:temperature:(0.0 0.3 0.5 0.7 1.0)'
        '--max-tokens[Max tokens]:max-tokens:'
        '--system[System prompt]:system:'
        '--stream[Enable streaming]'
    )

    local -a models_commands
    models_commands=(
        'list:List available models'
        'info:Show model info'
        'pull:Download model'
        'remove:Remove model'
    )

    _arguments -C \
        '1:command:->command' \
        '*::arg:->args'

    case $state in
        command)
            _describe 'command' commands
            ;;
        args)
            case $words[1] in
                chat|complete)
                    _arguments $chat_opts
                    ;;
                models)
                    _describe 'models command' models_commands
                    ;;
            esac
            ;;
    esac
}

# dc-web completion
_dc-web() {
    local -a commands
    commands=(
        'start:Start web dashboard'
        'stop:Stop web dashboard'
        'status:Show dashboard status'
    )

    local -a opts
    opts=(
        '--host[Host to bind to]:host:(localhost 0.0.0.0 127.0.0.1)'
        '--port[Port to listen on]:port:(8000 8080 3000 5000)'
        '--workers[Number of workers]:workers:'
        '--reload[Enable auto-reload]'
    )

    _arguments -C \
        '1:command:->command' \
        $opts

    case $state in
        command)
            _describe 'command' commands
            ;;
    esac
}

# dc-mesh completion
_dc-mesh() {
    local -a commands
    commands=(
        'start:Start mesh node'
        'stop:Stop mesh node'
        'join:Join mesh network'
        'leave:Leave mesh network'
        'peers:List peers'
        'status:Show mesh status'
        'discover:Discover peers'
    )

    local -a start_opts
    start_opts=(
        '--port[Port to listen on]:port:'
        '--bootstrap[Bootstrap peers]:bootstrap:'
        '--name[Node name]:name:'
        '--config[Configuration file]:config:_files -g "*.yaml *.yml"'
    )

    _arguments -C \
        '1:command:->command' \
        '*::arg:->args'

    case $state in
        command)
            _describe 'command' commands
            ;;
        args)
            case $words[1] in
                start)
                    _arguments $start_opts
                    ;;
            esac
            ;;
    esac
}

# dc-workflow completion
_dc-workflow() {
    local -a commands
    commands=(
        'run:Run a workflow'
        'list:List workflows'
        'status:Get workflow status'
        'cancel:Cancel workflow'
        'pause:Pause workflow'
        'resume:Resume workflow'
        'logs:View workflow logs'
        'visualize:Visualize workflow'
    )

    local -a run_opts
    run_opts=(
        '--file[Workflow file]:file:_files -g "*.yaml *.yml"'
        '--name[Workflow name]:name:'
        '--params[Parameters as JSON]:params:'
        '--dry-run[Dry run mode]'
    )

    _arguments -C \
        '1:command:->command' \
        '*::arg:->args'

    case $state in
        command)
            _describe 'command' commands
            ;;
        args)
            case $words[1] in
                run)
                    _arguments $run_opts
                    ;;
            esac
            ;;
    esac
}

# dc-secrets completion
_dc-secrets() {
    local -a commands
    commands=(
        'set:Set a secret'
        'get:Get a secret'
        'list:List secrets'
        'delete:Delete a secret'
        'rotate:Rotate a secret'
    )

    _arguments -C \
        '1:command:->command' \
        '*:secret name:'

    case $state in
        command)
            _describe 'command' commands
            ;;
    esac
}

# dc-inference completion
_dc-inference() {
    local -a commands
    commands=(
        'start:Start inference server'
        'stop:Stop inference server'
        'status:Show server status'
        'serve:Serve a model'
        'predict:Make prediction'
        'batch:Batch predictions'
    )

    local -a start_opts
    start_opts=(
        '--model[Model to serve]:model:'
        '--port[Port to listen on]:port:'
        '--workers[Number of workers]:workers:'
        '--gpu[GPU device]:gpu:'
        '--batch-size[Batch size]:batch-size:'
    )

    _arguments -C \
        '1:command:->command' \
        '*::arg:->args'

    case $state in
        command)
            _describe 'command' commands
            ;;
        args)
            case $words[1] in
                start|serve)
                    _arguments $start_opts
                    ;;
            esac
            ;;
    esac
}

# Completion dispatcher
_nebula() {
    local cmd=$words[1]

    case $cmd in
        dc-master)    _dc-master ;;
        dc-worker)    _dc-worker ;;
        dc-submit)    _dc-submit ;;
        dc-ai)        _dc-ai ;;
        dc-web)       _dc-web ;;
        dc-mesh)      _dc-mesh ;;
        dc-workflow)  _dc-workflow ;;
        dc-secrets)   _dc-secrets ;;
        dc-inference) _dc-inference ;;
    esac
}

# Register completions
compdef _dc-master dc-master
compdef _dc-worker dc-worker
compdef _dc-submit dc-submit
compdef _dc-ai dc-ai
compdef _dc-web dc-web
compdef _dc-mesh dc-mesh
compdef _dc-workflow dc-workflow
compdef _dc-secrets dc-secrets
compdef _dc-inference dc-inference
