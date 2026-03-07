"""XmlSitemapAdapter — stdlib xml.etree.ElementTree 기반 sitemap 생성."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from src.domain.ports.sitemap_port import SitemapPort
from src.domain.value_objects.sitemap_entry import SitemapEntry

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


class XmlSitemapAdapter(SitemapPort):
    """stdlib XML로 sitemap.xml 생성."""

    def generate(self, entries: list[SitemapEntry], output_path: str) -> str:
        urlset = ET.Element("urlset")
        urlset.set("xmlns", SITEMAP_NS)

        for entry in entries:
            url_el = ET.SubElement(urlset, "url")
            loc = ET.SubElement(url_el, "loc")
            loc.text = entry.url

            if entry.lastmod:
                lastmod = ET.SubElement(url_el, "lastmod")
                lastmod.text = entry.lastmod

            changefreq = ET.SubElement(url_el, "changefreq")
            changefreq.text = entry.changefreq

            priority = ET.SubElement(url_el, "priority")
            priority.text = f"{entry.priority:.1f}"

        tree = ET.ElementTree(urlset)
        ET.indent(tree, space="  ")
        tree.write(output_path, xml_declaration=True, encoding="UTF-8")
        return output_path
