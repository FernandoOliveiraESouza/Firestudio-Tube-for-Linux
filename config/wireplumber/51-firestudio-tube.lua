-- FireStudio Tube: always use the Pro Audio profile. DICE interfaces need
-- playback and capture opened together; the Multichannel profiles open them
-- separately and the output can fail with an I/O error.
-- Installed in ~/.config/wireplumber/main.lua.d/ by install.sh.

table.insert(alsa_monitor.rules, {
  matches = {
    {
      { "device.name", "equals", "alsa_card.firewire-0x000a92040310caa0" },
    },
  },
  apply_properties = {
    ["device.profile"] = "pro-audio",
  },
})
