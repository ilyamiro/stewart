const { Readability } = require('@mozilla/readability');
const path = require('path');
const { JSDOM } = require('jsdom');
const fs = require("fs")

const args = process.argv.slice(2)
const url = args[0];
const parentDir = path.dirname(path.dirname(__dirname));


function remove_space(str) {
    return str.replace(/[\s\n\r]+/g, ' ');
}

const main = async () => {
    const dom = await JSDOM.fromURL(url);
    const reader = new Readability(dom.window.document);
    const article = reader.parse();
    fs.writeFileSync(parentDir + '/text.txt', remove_space(article.title + " " + article.textContent))
}

main()
