#!/bin/sh
# Backups privados fora do volume do banco. Execute apenas uma instância.
set -eu
umask 077

backup_dir=${OTO_BACKUP_DIR:-/backups}
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"

backup() {
    stamp=$(date -u +%F)
    file="$backup_dir/oto-$stamp.dump"
    if [ ! -s "$file" ]; then
        tmp=$(mktemp "$backup_dir/.oto-XXXXXX")
        trap 'rm -f "$tmp"' EXIT
        pg_dump --format=custom --no-password --file="$tmp" || return 1
        pg_restore --list "$tmp" >/dev/null || return 1
        mv -f "$tmp" "$file" || return 1
        trap - EXIT
    fi
    find "$backup_dir" -maxdepth 1 -type f -name 'oto-????-??-??.dump' -mtime +29 -delete
}

if [ "${1:-}" = "--restore" ]; then
    stamp=${2:-}
    target=${3:-}
    case "$stamp" in
        [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;;
        *) echo 'Informe a data no formato AAAA-MM-DD.' >&2; exit 2 ;;
    esac
    case "$target" in
        oto_restore_*) ;;
        *) echo 'O nome da nova base deve começar com oto_restore_.' >&2; exit 2 ;;
    esac
    case "$target" in
        *[!a-z0-9_]*) echo 'Nome de base inválido.' >&2; exit 2 ;;
    esac
    [ "${#target}" -le 63 ] && [ "$target" != "${PGDATABASE:-}" ] || exit 2
    file="$backup_dir/oto-$stamp.dump"
    [ -s "$file" ] || { echo 'Backup indisponível.' >&2; exit 2; }
    # CREATE DATABASE exige um nome novo. Assim, um erro nunca sobrescreve uma base existente.
    createdb --no-password --maintenance-db="${PGDATABASE:-postgres}" "$target"
    pg_restore --no-password --single-transaction --no-owner --no-acl --dbname="$target" "$file"
    exit
fi

if [ "${1:-}" = "--once" ]; then
    backup
    exit
fi

# Acorda a cada hora e garante um snapshot por dia UTC, inclusive após reinício.
while true; do
    if ! (set -e; backup); then
        echo 'Falha no backup de banco; nova tentativa em uma hora.' >&2
    fi
    sleep 3600 &
    wait "$!"
done
