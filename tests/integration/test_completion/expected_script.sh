#!/usr/bin/env bash
# Bash completion script for testcraft
# This script was generated by the completion module of craft_cli. It should
# not be edited directly.

# shellcheck disable=2207

_complete_testcraft(){
  local cur prev all_cmds cmd
  all_cmds=( ls cp )
  cur="$2"
  prev="$3"
  # Remove "$cur" (the last element) from $COMP_WORDS
  COMP_WORDS=("${COMP_WORDS[@]:0:((${#COMP_WORDS[@]} - 1))}")
  # "=" gets lexed as its own word, so let the completion
  if [[ "${prev}" == "=" ]]; then
    prev="${COMP_WORDS[-2]}"
    COMP_WORDS=("${COMP_WORDS[@]:0:((${#COMP_WORDS[@]} - 1))}") # remove the last element
  fi
  # We can assume the first argument that doesn't start with a - is the command.
  for arg in "${COMP_WORDS[@]:1}"; do
    if [[ "${arg:0:1}" != "-" ]]; then
      cmd="${arg}"
      break
    elif [[ "${arg}" == "--help" ]]; then  # "--help" works the same as "help"
      cmd="help"
      break
    fi
  done

  # A function for completing each individual command.
  # Global arguments may be used either before or after the command name, so we
  # use those global arguments in each function.
  case "${cmd}" in
    ls)
      case "${prev}" in
        -h|--help)
          COMPREPLY=($(compgen -- "$cur"))
          return
          ;;
        --color)
          COMPREPLY=($(compgen -W 'always auto never' -- "$cur"))
          return
          ;;
        *)
          # Not in the middle of a command option, present all options.
          COMPREPLY=(
            $(compgen -W "-h --help -a --all --color" -- "$cur")
            $(compgen -o bashdefault -A file -- "$cur")
          )
          return
          ;;
      esac
      ;;
    cp)
      case "${prev}" in
        -h|--help)
          COMPREPLY=($(compgen -- "$cur"))
          return
          ;;
        *)
          # Not in the middle of a command option, present all options.
          COMPREPLY=(
            $(compgen -W "-h --help" -- "$cur")
            $(compgen -o bashdefault -A file -- "$cur")
          )
          return
          ;;
      esac
      ;;
  esac

  case "${prev}" in
    --verbosity)
      COMPREPLY=($(compgen -W 'quiet brief verbose debug trace' -- "$cur"))
      return
      ;;
  esac

  COMPREPLY=($(compgen -W "${all_cmds[*]} ${global_args[*]}" -- "$cur"))
}

complete -F _complete_testcraft testcraft
