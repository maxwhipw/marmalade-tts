"""Synthesis loop — runs an engine over one or more utterances.

Used by both cli.py (interactive / batch / streaming) and mcp_server.py
(single-call ``synthesize`` tool). Keeping the loop here means
preprocessing, effects, duration measurement, and ordering rules apply
uniformly to both entry points.

The streaming branch (``run_batch(streaming=True, on_ready=...)``) spawns
a producer thread that renders utterances sequentially and fires
``on_ready(result)`` for each one as it lands; the caller blocks on the
callback (typically to play the WAV). This is Option A from the refactor
spec — the (synth + queue + sentinel) coupling stays in one place and the
CLI just supplies a small playback consumer via the callback.

``wav_duration`` is looked up through the ``cli`` module at call time so
test patches on ``marmalade_tts.cli.wav_duration`` (used heavily by the
streaming tests) keep working after the refactor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import cli_helpers


@dataclass
class SynthResult:
    """One rendered utterance.

    Kept dict-compatible (via ``__getitem__``) because downstream helpers
    in ``cli_helpers`` (subtitles, --json reporting) were written against
    the dict shape the old ``_synthesize_one`` returned. Reusing the same
    access pattern lets the rest of the refactor stay a pure mechanical
    move."""

    out: str
    text: str         # post-preprocessing text actually sent to the engine
    raw_text: str     # original user input (used for subtitles)
    duration: float

    def __getitem__(self, key: str):
        return getattr(self, key)

    def get(self, key: str, default=None):
        return getattr(self, key, default)


def synthesize_one(
    utt: str,
    out_path: str,
    *,
    engine,
    engine_name: str,
    eng_cfg: dict,
    config: dict,
    synth_kwargs: dict,
    effect_list: list,
    preprocess_mode,        # None = use config default; True/False = force
    custom_rules: list | None,
) -> SynthResult | None:
    """Synthesize a single utterance: preprocess → synth → effects → measure.

    ``preprocess_mode``:
      * ``None`` — use the same config-driven default the CLI uses
        (``defaults.preprocessing`` plus per-engine overrides).
      * ``True`` / ``False`` — force preprocessing on or off, ignoring
        config. Used by MCP (always True) and by ``--preprocessing`` /
        ``--no-preprocessing``.

    ``custom_rules`` overrides the per-engine default rule set when given;
    ``None`` means "use the engine's defaults". Matches the legacy
    ``eng_cfg.get('preprocessing')``-as-list behavior the CLI inherits.

    Returns ``None`` when the preprocessed text is empty (whitespace-only
    line, or stripped to nothing) — the caller should skip it silently to
    preserve batch behavior.
    """
    # Lazy import to avoid module-load circular: cli imports synth, synth
    # only needs cli's namespace at call time (for the patchable
    # ``wav_duration`` reference the streaming tests rely on).
    from . import cli
    from . import preprocessing as pp

    # ── Preprocessing ──
    if preprocess_mode is True:
        do_preprocess = True
    elif preprocess_mode is False:
        do_preprocess = False
    else:
        do_preprocess = config.get("defaults", {}).get("preprocessing", True)
        eng_pp = eng_cfg.get("preprocessing")
        if eng_pp is not None:
            if isinstance(eng_pp, bool):
                do_preprocess = eng_pp
            elif isinstance(eng_pp, list):
                do_preprocess = True

    if do_preprocess:
        rules = custom_rules
        if rules is None:
            cfg_rules = eng_cfg.get("preprocessing")
            if isinstance(cfg_rules, list):
                rules = cfg_rules
        if rules is not None:
            processed = pp.preprocess(utt, engine=engine_name, rules=rules)
        else:
            processed = pp.preprocess(utt, engine=engine_name)
    else:
        processed = utt

    if not processed.strip():
        return None

    # ── Synthesis + effects ──
    engine.synthesize(processed, out_path, **synth_kwargs)
    cli_helpers.apply_effects_if_any(out_path, effect_list, config)

    # ── Duration (AFTER effects — sox tempo/speed/fade change length). ──
    try:
        duration = cli.wav_duration(out_path)
    except Exception:
        duration = 0.0

    return SynthResult(
        out=out_path,
        text=processed,
        raw_text=utt,
        duration=duration,
    )


def run_batch(
    utterances: list[str],
    out_paths: list[str],
    *,
    engine,
    engine_name: str,
    eng_cfg: dict,
    config: dict,
    synth_kwargs: dict,
    effect_list: list,
    preprocess_mode=None,
    custom_rules: list | None = None,
    streaming: bool = False,
    on_ready: Callable[[SynthResult], None] | None = None,
    on_interrupt: Callable[[SynthResult], None] | None = None,
) -> tuple[list[SynthResult], BaseException | None]:
    """Run synthesis over a batch.

    When ``streaming=False`` (or ``on_ready`` is not given), runs
    sequentially and returns ``(results, None)`` — exceptions propagate.

    When ``streaming=True`` and ``on_ready`` is given, spawns a producer
    thread (``marmalade-producer``) that renders sequentially, and fires
    ``on_ready(result)`` for each utterance as it lands. The callback runs
    in the caller's thread, so the caller can do blocking work (like
    ``play_wav``) and still overlap with the next render.

    If the producer raises, the consumer finishes draining what's already
    in the queue, then ``run_batch`` returns ``(partial_results, exc)`` —
    it does NOT re-raise. The caller decides whether to re-raise (cli does).

    ``on_interrupt(result)`` is called for each queued-but-unplayed result
    when the consumer receives a ``KeyboardInterrupt`` — lets the caller
    clean up tmp WAVs that won't be touched again. The interrupt then
    propagates out of ``run_batch``.
    """
    if not streaming or on_ready is None:
        # Simple sequential path — no thread.
        results: list[SynthResult] = []
        for utt, out_path in zip(utterances, out_paths):
            r = synthesize_one(
                utt, out_path,
                engine=engine, engine_name=engine_name,
                eng_cfg=eng_cfg, config=config,
                synth_kwargs=synth_kwargs, effect_list=effect_list,
                preprocess_mode=preprocess_mode, custom_rules=custom_rules,
            )
            if r is not None:
                results.append(r)
        return results, None

    # ── Streaming: producer thread + queue, consumer in caller's thread. ──
    import queue
    import threading

    play_q: "queue.Queue" = queue.Queue()
    results: list[SynthResult] = []
    producer_error: list[BaseException] = []

    def _produce():
        try:
            for utt, out_path in zip(utterances, out_paths):
                r = synthesize_one(
                    utt, out_path,
                    engine=engine, engine_name=engine_name,
                    eng_cfg=eng_cfg, config=config,
                    synth_kwargs=synth_kwargs, effect_list=effect_list,
                    preprocess_mode=preprocess_mode, custom_rules=custom_rules,
                )
                if r is None:
                    continue
                results.append(r)
                play_q.put(r)
        except BaseException as e:
            producer_error.append(e)
        finally:
            play_q.put(None)  # sentinel: end of stream

    prod = threading.Thread(
        target=_produce, daemon=True, name="marmalade-producer")
    prod.start()

    # Consumer: drain queue in FIFO (= input) order, hand to on_ready.
    try:
        while True:
            r = play_q.get()
            if r is None:
                break
            on_ready(r)
    except KeyboardInterrupt:
        # Producer is a daemon thread, so it dies with the process; we
        # just notify the caller about whatever was already enqueued so
        # tmp files can be cleaned up.
        if on_interrupt is not None:
            try:
                while True:
                    leftover = play_q.get_nowait()
                    if leftover is None:
                        continue
                    on_interrupt(leftover)
            except queue.Empty:
                pass
        raise

    prod.join()
    return results, (producer_error[0] if producer_error else None)
