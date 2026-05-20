# Frontend npm commands

frontend := source_directory() / ".." / "frontend"

[group('npm')]
install:
    cd "{{frontend}}" && npm install

[group('npm')]
dev:
    cd "{{frontend}}" && npm run dev

[group('npm')]
build:
    cd "{{frontend}}" && npm run build

[group('npm')]
run *args:
    cd "{{frontend}}" && npm {{args}}
