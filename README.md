# FireStudio Tube no Linux

Substituto do PreSonus Universal Control para a FireStudio Tube (FireWire, chip TCAT DICE II).

## Como funciona

| Peça | O que faz |
|---|---|
| `snd_dice` (kernel) | Driver de áudio: 16 entradas, 8 saídas (já vem no Linux) |
| `snd-dice-ctl-service` (`src/snd-firewire-ctl-services`) | Expõe o roteador e o mixer DSP da placa como controles ALSA. Roda como serviço systemd do usuário: `firestudio-tube-ctl` |
| `firestudio-control` | Painel no estilo do Universal Control (manual, seção 3.1.4) |
| `config/pipewire/firestudio-tube.conf` | Uma saída de som, "FireStudio Tube" (DAW 1-2), como o WDM do Windows |
| `config/wireplumber/51-firestudio-tube.lua` | Fixa o perfil **Pro Audio** (os perfis Multichannel falham com a DICE) |

No sistema aparece uma única saída de som, **FireStudio Tube** (canais DAW 1-2), como no
Windows. Para onde ela vai é decidido no painel: cada saída física (Main, Out 3-4, Out 5-6,
Fones) tem uma mix com latência zero em que DAW 1-2 é um canal com fader, pan, mute e solo.
No preset **Padrão**, DAW 1-2 toca em todas as saídas a 0 dB e os Fones também têm a
monitoração das entradas. Com o botão **Mixer** desligado, a saída recebe direto os canais DAW
dela (Main = 1-2, Out 3-4 = 3-4, …). DAWs que usam a saída Pro Audio de 8 canais enviam DAW 3-8.

**Sample rate e buffer** ficam na aba Configurações (como a Launch Window do Universal
Control). No Linux quem abre a placa é o PipeWire, então o painel ajusta o PipeWire na hora
(`pw-metadata`) e grava `~/.config/pipewire/pipewire.conf.d/firestudio-tube-clock.conf` para o
próximo boot. A placa guarda roteamento/mixer separados para 44,1/48 kHz e 88,2/96 kHz e os
recarrega da memória ao trocar de taxa; por isso o painel reaplica, grava e confere a
configuração depois de cada troca (`tube.apply_and_store`).

O roteamento e as mixes ficam na placa. **Gravar na placa** (aba Presets) os salva na memória
dela, e o serviço também salva sozinho quando para (ao desligar o PC).

## Comandos úteis

```
firestudio-control                              # painel
systemctl --user restart firestudio-tube-ctl    # reinicia o serviço (e grava na placa)
python3 tube.py                                 # mostra o roteamento atual
python3 tube.py apply presets/padrao.json      # aplica um preset
python3 tube.py save presets/meu.json           # salva o estado atual
```

`presets/original-da-placa.json` é o estado que estava gravado na placa antes (do Universal
Control no Windows); `backup/` tem o dump completo dos controles.

## Instalação

Testado no Linux Mint 22 / Ubuntu 24.04 (PipeWire 1.0, WirePlumber 0.4).

1. Pacotes do sistema e Rust ([rustup.rs](https://rustup.rs)):
   ```
   sudo apt install git meson ninja-build libudev-dev gobject-introspection \
       libgirepository1.0-dev libhinawa-dev libhitaki-dev libasound2-dev
   ```
2. Clone este repositório em `~/firestudio-tube` (o serviço systemd usa esse caminho) e rode:
   ```
   sh install.sh
   ```
   Ele baixa e compila [alsa-gobject](https://github.com/alsa-project/alsa-gobject) (em
   `~/.local`) e [snd-firewire-ctl-services](https://github.com/alsa-project/snd-firewire-ctl-services)
   em `src/`, instala as configs do PipeWire/WirePlumber, o serviço e o atalho no menu.

`config/pipewire/firestudio-tube.conf` e `config/wireplumber/51-firestudio-tube.lua` usam o GUID
desta placa (`0x000a92040310caa0`); com outra unidade, troque pelo da sua
(`pactl list cards short | grep firewire`).

O preset `presets/original-da-placa.json` é a configuração que veio na placa deste projeto;
para guardar a da sua antes de mexer: `python3 tube.py save presets/minha-placa.json`.

## Créditos

O controle da placa é feito pelo `snd-dice-ctl-service`, do projeto
[snd-firewire-ctl-services](https://github.com/alsa-project/snd-firewire-ctl-services)
(Takashi Sakamoto), que não faz parte deste repositório.

## Licença

MIT — veja [LICENSE](LICENSE).
