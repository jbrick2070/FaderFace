// FaderFace: queue one run per knob move.
//
// ComfyUI's Auto Queue has two modes and neither fits a MIDI controller:
// "instant" re-runs the graph forever (the preview strobes), and "change"
// only reacts to widgets a person edits, so the MIDI loader writing its
// hidden raw_data value never counts. This extension listens to every MIDI
// input itself and queues a run when a knob, fader or pad moves, with at
// most one run in flight and one pending, so the last knob position always
// renders and nothing stacks up. Leave Auto Queue OFF.
//
// It only acts while the open graph contains an APC40 Knob or APC40 Pad node,
// so other workflows are untouched.
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const MIN_GAP_MS = 60;          // never queue faster than this
const LOADER_SETTLE_MS = 20;    // let the MIDI loader write raw_data first
const STUCK_MS = 15000;         // forget a run we never heard finish

app.registerExtension({
    name: "FaderFace.QueueOnKnob",
    async setup() {
        if (!navigator.requestMIDIAccess) {
            console.warn("[FaderFace] Web MIDI is not available in this browser");
            return;
        }

        let running = false;
        let pending = false;
        let lastQueued = 0;
        let timer = null;
        let startedAt = 0;
        const attached = new WeakSet();

        const usesFaderFace = () =>
            (app.graph?._nodes || []).some((n) => n.type === "APC40Knob" || n.type === "APC40Pad");

        const queueNow = () => {
            timer = null;
            running = true;
            pending = false;
            lastQueued = performance.now();
            startedAt = lastQueued;
            app.queuePrompt(0, 1);
        };

        const kick = () => {
            if (!usesFaderFace()) return;
            if (running && performance.now() - startedAt < STUCK_MS) {
                pending = true;
                return;
            }
            if (timer !== null) return;
            const gap = Math.max(0, MIN_GAP_MS - (performance.now() - lastQueued));
            timer = setTimeout(queueNow, gap + LOADER_SETTLE_MS);
        };

        const finished = () => {
            running = false;
            if (pending) kick();
        };
        api.addEventListener("execution_success", finished);
        api.addEventListener("execution_error", finished);
        api.addEventListener("execution_interrupted", finished);

        const onMidi = (event) => {
            const type = event.data[0] >> 4;
            if (type === 0xb || type === 0x9 || type === 0x8) kick();   // CC, note on, note off
        };
        const attach = (input) => {
            if (attached.has(input)) return;
            attached.add(input);
            input.addEventListener("midimessage", onMidi);
        };

        try {
            const access = await navigator.requestMIDIAccess();
            for (const input of access.inputs.values()) attach(input);
            access.addEventListener("statechange", (event) => {
                if (event.port.type === "input" && event.port.state === "connected") attach(event.port);
            });
            console.log("[FaderFace] queue-on-knob armed for", access.inputs.size, "MIDI input(s)");
        } catch (error) {
            console.warn("[FaderFace] Web MIDI access refused:", error);
        }
    },
});
