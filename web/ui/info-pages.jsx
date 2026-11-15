import React, {useLayoutEffect} from "react";
import about from "./content/about.md";
import aboutEn from "./content/about.en.md";
import how from "./content/how.md";
import howEn from "./content/how.en.md";
import contribute from "./content/contribute.md";
import contributeEn from "./content/contribute.en.md";
import {tr, href} from "./locale.js";

export const infoPages = {
  about: {label: tr("소개", "About"), html: tr(about, aboutEn)},
  how: {label: tr("방법", "How it works"), html: tr(how, howEn)},
  contribute: {label: tr("기여하기", "Contribute"), html: tr(contribute, contributeEn)},
};

export function InfoNav({currentPage, className = "mast-nav", label = tr("사이트 메뉴", "Site navigation")}) {
  return <nav className={className} aria-label={label}>
    {Object.entries(infoPages).map(([key, {label}]) => <a key={key} href={href(`/?page=${key}`)}
      aria-current={currentPage === key ? "page" : undefined}>{label}</a>)}
  </nav>;
}

function splitPage(html, page) {
  // The build renders Markdown with raw HTML and unsafe URLs disabled.
  const template = document.createElement("template");
  template.innerHTML = html;
  for (const link of template.content.querySelectorAll('a[href^="/"]:not([href^="//"])')) {
    link.setAttribute("href", href(link.getAttribute("href")));
  }
  const intro = [];
  const sections = [];
  const footer = [];
  let block = intro;
  for (const element of template.content.children) {
    if (block !== footer && element.tagName === "HR") {
      block = footer;
      continue;
    }
    if (block !== footer && element.tagName === "H2") {
      if (page === "about" && element.textContent.replace(/^\d+\.\s*/, "") === tr("권리 안내 및 문의", "Rights and contact")) {
        element.id = "rights";
        element.tabIndex = -1;
      }
      block = [];
      sections.push(block);
    }
    block.push(element.outerHTML);
  }
  return {intro: intro.join("\n"), sections: sections.map(section => section.join("\n")), footer: footer.join("\n")};
}

export function InfoPage({page}) {
  const {intro, sections, footer} = splitPage(infoPages[page].html, page);
  useLayoutEffect(() => {
    if (page === "about" && window.location.hash === "#rights") {
      document.getElementById("rights")?.focus();
    }
  }, [page]);
  return <main className="shell info-page">
    <header dangerouslySetInnerHTML={{__html: intro}} />
    {sections.length > 0 && <div className="info-sections">
      {sections.map((html, index) => <section key={index} dangerouslySetInnerHTML={{__html: html}} />)}
    </div>}
    {footer && <footer dangerouslySetInnerHTML={{__html: footer}} />}
  </main>;
}
