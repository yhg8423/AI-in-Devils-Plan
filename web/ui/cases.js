import {tr} from "./locale.js";

export function caseMatches({matches, exile_matches: exileMatches = []}) {
  const stageOrder = new Map(matches.map(({id}, index) => [id, index]));
  const position = ({id, after}) => stageOrder.get(id) ?? ((stageOrder.get(after) ?? matches.length) + 0.5);
  return [...matches, ...exileMatches].sort((first, second) => position(first) - position(second));
}

function modelName(id) {
  const family = id?.match(/^gpt-\d+(?:\.\d+)?-(luna|sol|terra|astra)$/)?.[1];
  return family ? family[0].toUpperCase() + family.slice(1) : id;
}

function caseLabel(record) {
  if (!record.model) return tr("스크립트 실행", "Scripted run");
  const settings = ({model, effort}) => [modelName(model), effort].filter(Boolean).join(" ");
  return [...new Set([record, ...Object.values(record.model_overrides ?? {})].map(settings))].join(" + ");
}

export function caseTitle(record) {
  const models = new Set([record, ...Object.values(record.model_overrides ?? {})].map(({model}) => modelName(model)));
  if (models.size >= 3) {
    return tr("다양한 종류의 모델이 겨룹니다.", "A variety of models compete.");
  }
  if (models.has("Luna") && models.has("Sol")) {
    return tr("플래그십 모델과 가벼운 모델이 겨룹니다.", "Flagship and lightweight models compete.");
  }
  if (models.size === 1 && models.has("Sol")) {
    return tr("플래그십 모델들이 겨룹니다.", "Flagship models compete.");
  }
  if (models.size === 1 && models.has("Luna")) {
    return tr("빠르고 가벼운 모델이 겨룹니다.", "Fast, lightweight models compete.");
  }
  return caseLabel(record);
}
