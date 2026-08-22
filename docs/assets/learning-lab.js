(() => {
  const stageDetails = {
    input: {
      title: "1 · Input is evidence, not an expense",
      body: "The package accepts JPG, PNG, or WebP. Pillow fixes EXIF orientation and converts the image into a predictable RGB representation. No database record is created here.",
    },
    prepare: {
      title: "2 · OpenCV makes two useful views",
      body: "The code deskews, resizes, normalizes grayscale, and creates an adaptive-threshold copy. Different views help OCR survive dark themes, compression, and uneven contrast.",
    },
    read: {
      title: "3 · Tesseract reads; pytesseract carries messages",
      body: "Tesseract is the recognition engine. pytesseract is only the Python wrapper. Each image view is read in English and Devanagari with page-segmentation modes 4, 6, and 11.",
    },
    rank: {
      title: "4 · Python decides which number means payment",
      body: "The parser normalizes Unicode digits, extracts money candidates, rewards labels such as “Amount Paid” and “To Pay,” demotes intermediate totals, and groups agreement across passes using Decimal amounts.",
    },
    guard: {
      title: "5 · Evidence controls confidence",
      body: "A result becomes strong only when independent evidence agrees and competing totals are safely behind. Ambiguity produces review. Every grade still sets requires_confirmation to true.",
    },
    benchmark: {
      title: "6 · The benchmark judges the system",
      body: "Expected labels are compared with detected total and currency. The formal gate needs 30 authorized screenshots, at least 90% exact matches, zero wrong strong suggestions, and confirmation on every case.",
    },
  };

  document.querySelectorAll("[data-stage]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-stage]").forEach((candidate) => {
        candidate.setAttribute("aria-pressed", String(candidate === button));
      });
      const detail = stageDetails[button.dataset.stage];
      const target = document.querySelector("[data-stage-detail]");
      target.innerHTML = `<h3>${detail.title}</h3><p>${detail.body}</p>`;
    });
  });

  let correctAnswers = 0;
  const completed = new Set();
  document.querySelectorAll("[data-quiz]").forEach((quiz, quizIndex) => {
    const feedback = quiz.querySelector("[data-feedback]");
    quiz.querySelectorAll("[data-answer]").forEach((button) => {
      button.addEventListener("click", () => {
        quiz.querySelectorAll("[data-answer]").forEach((candidate) => {
          candidate.classList.remove("correct", "incorrect");
        });
        const isCorrect = button.dataset.answer === "correct";
        button.classList.add(isCorrect ? "correct" : "incorrect");
        feedback.className = `feedback ${isCorrect ? "good" : "try-again"}`;
        feedback.textContent = isCorrect
          ? button.dataset.correctFeedback
          : button.dataset.incorrectFeedback;
        if (isCorrect && !completed.has(quizIndex)) {
          completed.add(quizIndex);
          correctAnswers += 1;
          document.querySelectorAll("[data-score]").forEach((score) => {
            score.textContent = `${correctAnswers} / ${document.querySelectorAll("[data-quiz]").length}`;
          });
        }
      });
    });
  });

  const teachBack = document.querySelector("[data-teach-back]");
  if (teachBack) {
    const keywords = [
      {
        label: "image preparation",
        pattern: /pillow|opencv|preprocess|deskew|threshold/i,
      },
      {
        label: "Tesseract reads",
        pattern: /tesseract|ocr engine|reads? text/i,
      },
      {
        label: "candidate ranking",
        pattern: /rank|candidate|label|to pay|amount paid/i,
      },
      { label: "confirmation", pattern: /confirm|confirmation|human review/i },
      {
        label: "systems separate",
        pattern: /separate|not integrated|future service|boundary/i,
      },
    ];
    const chips = document.querySelector("[data-keywords]");
    chips.innerHTML = keywords
      .map(
        (keyword, index) =>
          `<span class="keyword" data-keyword="${index}">${keyword.label}</span>`,
      )
      .join("");
    teachBack.addEventListener("input", () => {
      const value = teachBack.value;
      let found = 0;
      keywords.forEach((keyword, index) => {
        const matched = keyword.pattern.test(value);
        chips
          .querySelector(`[data-keyword="${index}"]`)
          .classList.toggle("found", matched);
        found += matched ? 1 : 0;
      });
      document.querySelector("[data-progress]").style.width =
        `${(found / keywords.length) * 100}%`;
      const feedback = document.querySelector("[data-teach-feedback]");
      feedback.textContent =
        found === keywords.length
          ? "Strong teach-back. You covered the full flow and the current system boundary."
          : `${found} of ${keywords.length} architectural ideas recovered from memory.`;
      feedback.className = `feedback ${found === keywords.length ? "good" : ""}`;
    });
  }
})();
