import re

from selectolax.parser import HTMLParser, Node

from taxguide.crawling.models import WizardMetadata
from taxguide.domain.enums import PageType


def _clean_text(node: Node | None) -> str | None:
    if node is None:
        return None
    text = " ".join(node.text(separator=" ", strip=True).split())
    return text or None


def classify_page(html: str) -> tuple[PageType, WizardMetadata | None]:
    tree = HTMLParser(html)
    roots = tree.css(".wizardstartpage, .wizards, #vue-advanced-wizard")
    steps = tree.css('[data-wizard-step-type="question"]')
    script_wizard_id = re.search(r"\bvar\s+id\s*=\s*[\"']?([\w-]+)", html)
    is_wizard = bool(roots or steps)
    if is_wizard:
        ids: list[str] = []
        for root in roots:
            value = root.attributes.get("data-wizard-id") or root.attributes.get("id")
            if value and value != "vue-advanced-wizard" and value not in ids:
                ids.append(value)
        if script_wizard_id and script_wizard_id.group(1) not in ids:
            ids.append(script_wizard_id.group(1))
        first = steps[0] if steps else None
        step_id = first.attributes.get("data-stepid") if first else None
        question = None
        answers: list[str] = []
        if first:
            question = _clean_text(first.css_first("legend, h1, h2, h3, .question, p"))
            for answer in first.css("label, button, option"):
                label = _clean_text(answer)
                if label and label not in answers:
                    answers.append(label)
        return PageType.INTERACTIVE_WIZARD, WizardMetadata(
            wizard_ids=ids,
            first_visible_step_id=step_id,
            initial_question=question,
            initial_answer_labels=answers,
            only_initial_rendered_step=len(steps) <= 1,
        )
    if tree.css_first("[data-vue-app], [data-reactroot], #__next"):
        return PageType.UNKNOWN_DYNAMIC, None
    return PageType.STATIC_ARTICLE, None


def language_hint(html: str) -> str | None:
    tree = HTMLParser(html)
    root = tree.css_first("html")
    language = root.attributes.get("lang") if root else None
    if language:
        return language.strip() or None
    meta = tree.css_first('meta[http-equiv="content-language"], meta[name="language"]')
    value = meta.attributes.get("content") if meta else None
    return value.strip() if value and value.strip() else None
