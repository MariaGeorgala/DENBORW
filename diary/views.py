from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count

from .models import MoodEntry
from mood.llm import (
    analyze_conversation_with_llm,
    generate_adaptive_question,
    generate_followup_question
)

MAX_QUESTIONS = 5


def home(request):
    return render(request, "diary/home.html")


@login_required
def log_mood(request):

    # Αρχικοποίηση session
    if "answers" not in request.session:
        request.session["answers"] = []
        request.session["step"] = 1

        last_entries = MoodEntry.objects.filter(
            user=request.user
        ).order_by("-date")[:3]

        emotion_memory = [e.mood for e in last_entries]
        request.session["emotion_memory"] = emotion_memory

        question = generate_adaptive_question(
            previous_answers=[],
            step=1,
            emotion_memory=emotion_memory
        )
        request.session["current_question"] = question

    answers = request.session.get("answers", [])
    step = request.session.get("step", 1)
    question = request.session.get("current_question", "")

    if request.method == "POST":

        # Αν πατήσει "Θέλω να σταματήσω"
        if "stop" in request.POST:
            return finalize_mood(request, answers)

        answer = request.POST.get("response")

        if not answer:
            return render(request, "diary/log_mood.html", {
                "question": question,
                "error": "Γράψε μια απάντηση 🙂",
                "step": step
            })

        answers.append(answer)
        request.session["answers"] = answers
        request.session["step"] = step + 1

        # Αν έφτασε το μέγιστο πλήθος ερωτήσεων
        if len(answers) >= MAX_QUESTIONS:
            return finalize_mood(request, answers)

        # Επόμενη ερώτηση
        if step % 2 == 0:
            next_question = generate_followup_question(answers)
        else:
            next_question = generate_adaptive_question(
                previous_answers=answers,
                step=step + 1,
                emotion_memory=request.session.get("emotion_memory", [])
            )

        request.session["current_question"] = next_question
        return redirect("log_mood")

    return render(request, "diary/log_mood.html", {
        "question": question,
        "step": step
    })


def finalize_mood(request, answers):

    result = analyze_conversation_with_llm(answers)

    try:
        emotion, score = result.split("-")
        emotion = emotion.strip()
        score = int(score.strip())
    except:
        emotion = "ουδέτερο"
        score = 5

    score = max(0, min(score, 10))

    MoodEntry.objects.create(
        user=request.user,
        mood=emotion,
        score=score,
        response=str(answers)
    )

    # Καθαρισμός session
    for key in ["answers", "step", "current_question", "emotion_memory"]:
        request.session.pop(key, None)

    if score < 4:
        score_class = "low"
    elif score < 7:
        score_class = "medium"
    elif score < 9:
        score_class = "high"
    else:
        score_class = "extreme"

    return render(request, "diary/result.html", {
        "emotion": emotion,
        "score": score,
        "score_percent": score * 10,
        "score_class": score_class
    })


@login_required
def history_view(request):
    entries = MoodEntry.objects.filter(user=request.user).order_by("-date")
    return render(request, "diary/history.html", {
        "entries": entries
    })


@login_required
def stats_view(request):
    entries = MoodEntry.objects.filter(user=request.user)

    avg_score = entries.aggregate(Avg("score"))["score__avg"]
    mood_counts = entries.values("mood").annotate(total=Count("mood"))

    return render(request, "diary/stats.html", {
        "avg_score": avg_score,
        "mood_counts": mood_counts
    })
