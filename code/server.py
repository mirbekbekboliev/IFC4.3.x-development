import re
import os
import sys
import copy
import uuid
import glob
import json
import html
import shutil
import hashlib
import operator
import itertools
import subprocess

from collections import defaultdict, Counter
from dataclasses import dataclass
from functools import lru_cache

import tabulate
import pydot
import pysolr
import markdown

import bs4

# we depend on dictionaries with insertion order
assert sys.version_info[0:2] >= (3, 6)


def BeautifulSoup(*args):
    return bs4.BeautifulSoup(*args, features="lxml")


from flask import (
    Flask,
    send_file,
    render_template,
    render_template_string,
    abort,
    url_for,
    request,
    send_from_directory,
    jsonify,
)

import md as mdp
from extract_concepts_from_xmi import parse_bindings

app = Flask(__name__)

base = "/IFC/RELEASE/IFC4x3/HTML"


def make_url(fragment=None):
    return base + "/" + fragment if fragment else "/"


identity = lambda x: x

REPO_DIR = os.path.abspath(os.environ.get("REPO_DIR", os.path.join(os.path.dirname(__file__), "..")))


class schema_resource:
    def __init__(self, path, transform=identity):
        self.path = path
        self.transform = transform
        self.mtime = 0
        self.data = None

    def load(fn):
        def inner(self, *args):
            try:
                mt = os.path.getmtime(self.path)
                if mt > self.mtime:
                    self.data = self.transform(json.load(open(self.path, encoding="utf-8")))
                    self.mtime = mt
            except:
                print("Path", self.path, "not available")
                abort(503)

            return fn(self, *args)

        return inner

    @load
    def __getitem__(self, k):
        return self.data[k]

    @load
    def __contains__(self, k):
        return k in self.data

    @load
    def get(self, k, default=None):
        return self.data.get(k, default)

    @load
    def items(self):
        return self.data.items()

    @load
    def keys(self):
        return self.data.keys()

    @load
    def values(self):
        return self.data.values()


class resource_manager:
    entity_attributes = schema_resource("entity_attributes.json")
    entity_definitions = schema_resource("entity_definitions.json")
    entity_to_package = schema_resource("entity_to_package.json")
    entity_supertype = schema_resource("entity_supertype.json")
    entity_where_clauses = schema_resource("entity_where_clauses.json")
    pset_definitions = schema_resource("pset_definitions.json")
    changes_by_type = schema_resource("changes_by_type.json")
    deprecated_entities = schema_resource("deprecated_entities.json", transform=set)
    abstract_entities = schema_resource("abstract_entities.json", transform=set)
    type_values = schema_resource("type_values.json")
    hierarchy = schema_resource("hierarchy.json")
    xmi_concepts = schema_resource("xmi_concepts.json")
    examples_by_type = schema_resource("examples_by_type.json")


R = resource_manager()


def resource_paths(pairs, path=None):
    if isinstance(pairs, dict):
        pairs = list(pairs.items())
    if isinstance(pairs[0], str):
        for v in pairs:
            yield v, path
        return
    for p, vs in pairs:
        yield from resource_paths(vs, (path or ()) + ((p.split(" ")[0].lower() if path is None else p),))


def get_resource_path(resource, abort_on_error=True):
    v = dict(resource_paths(R.hierarchy)).get(resource)
    if not v:
        if abort_on_error:
            return abort(404)
        else:
            return None
    return (
        os.path.join(REPO_DIR, "docs/schemas", *v, resource + ".md")
        .replace("Property Sets", "PropertySets")
        .replace("Quantity Sets", "QuantitySets")
        .replace("Rules", "GlobalRules")
    )


navigation = [
    [
        {"name": "Cover", "url": make_url()},
        {"name": "Contents", "url": make_url("toc.html")},
        {"name": "Foreword", "url": make_url("content/foreword.htm")},
        {"name": "Introduction", "url": make_url("content/introduction.htm")},
    ],
    [
        {"number": 1, "name": "Scope", "url": make_url("content/scope.htm")},
        {"number": 2, "name": "Normative references", "url": make_url("content/normative_references.htm")},
        {
            "number": 3,
            "name": "Terms, definitions, and abbreviated terms",
            "url": make_url("content/terms_and_definitions.htm"),
        },
        {"number": 4, "name": "Fundamental concepts and assumptions", "url": make_url("concepts/content.html")},
        {"number": 5, "name": "Core data schemas", "url": make_url("chapter-5")},
        {"number": 6, "name": "Shared element data schemas", "url": make_url("chapter-6")},
        {"number": 7, "name": "Domain specific data schemas", "url": make_url("chapter-7")},
        {"number": 8, "name": "Resource definition data schemas", "url": make_url("chapter-8")},
    ],
    [
        {"number": "A", "name": "Computer interpretable listings", "url": make_url("annex-a.html")},
        {"number": "B", "name": "Alphabetical listings", "url": make_url("annex-b.html")},
        {"number": "C", "name": "Inheritance listings", "url": make_url("annex-c.html")},
        {"number": "D", "name": "Diagrams", "url": make_url("annex-d.html")},
        {"number": "E", "name": "Examples", "url": make_url("annex-e.html")},
        {"number": "F", "name": "Change logs", "url": make_url("annex-f.html")},
    ],
    [
        {"name": "Bibliography", "url": make_url("content/bibliography.htm")},
        # What is this? It's a broken link.
        {"name": "Index", "url": make_url("index.htm")},
    ],
]


def get_navigation(resource=None, number=None):
    if not number and resource:
        number = name_to_number()[resource]
    numbers = []
    if isinstance(number, str):
        numbers = number.split(".")
        number = int(numbers[0])
    for section in navigation:
        for item in section:
            item["subitems"] = []
            if item["url"] == request.path:
                item["is_current"] = True
            elif number and item.get("number", None) == number:
                item["is_current"] = True
                if number in (5, 6, 7, 8) and len(numbers) >= 2:
                    subchapters = [items for t, items in R.hierarchy if t == item["name"]][0]
                    for i, subchapter in enumerate(subchapters, 1):
                        data = {
                            "url": url_for("schema", name=subchapter[0].lower()),
                            "number": f"{number}.{i}",
                            "name": subchapter[0],
                        }
                        if i == int(numbers[1]):
                            data["is_current"] = True
                        item["subitems"].append(data)
            else:
                item["is_current"] = False
    return navigation


@dataclass(order=True, eq=True, frozen=True)
class toc_entry:
    text: str

    number: str = None
    url: str = None

    parent: object = None
    children: list = None


content_names = ["scope", "normative_references", "terms_and_definitions", "concepts"]
content_names_2 = ["cover", "foreword", "introduction", "bibliography"]


def chapter_lookup(number=None, cat=None):
    def do_chapter_lookup(x):
        if isinstance(x, (list, tuple)):
            return next((v for v in map(do_chapter_lookup, x) if v is not None), None)
        if number is not None and x.get("number", None) == number:
            return x
        if cat is not None and x["name"].split(" ")[0].lower() == cat:
            return x

    return do_chapter_lookup(navigation)


entity_names = lambda: sorted(sum([schema.get("Entities", []) for _, cat in R.hierarchy for __, schema in cat], []))
type_names = lambda: sorted(sum([schema.get("Types", []) for _, cat in R.hierarchy for __, schema in cat], []))


@lru_cache()
def name_to_number():
    ntn = {}

    for i, (cat, schemas) in enumerate(R.hierarchy, start=5):
        for j, (schema_name, members) in enumerate(schemas, start=1):
            for k, ke in enumerate(
                ["Types", "Entities", "Property Sets", "Quantity Sets", "Functions", "Rules"], start=2
            ):
                for l, name in enumerate(members.get(ke, ()), start=1):
                    ntn[name] = ".".join(map(str, (i, j, k, l)))

    return ntn


def get_inheritance_graph(current_entity):
    graph = []

    tier = []
    for subclass in sorted([k for k, v in R.entity_supertype.items() if v == current_entity]):
        tier.append(
            {
                "name": subclass,
                "is_deprecated": subclass in R.deprecated_entities,
                "is_abstract": subclass in R.abstract_entities,
            }
        )
    if tier:
        graph.append(tier)

    previous = None
    entity = current_entity
    while entity:
        tier = []
        parent = R.entity_supertype.get(entity, None)
        if parent:
            siblings = sorted([k for k, v in R.entity_supertype.items() if v == parent])
        else:
            siblings = [entity]
        for sibling in siblings:
            data = {
                "name": sibling,
                "is_deprecated": sibling in R.deprecated_entities,
                "is_abstract": sibling in R.abstract_entities,
                "is_current": sibling == current_entity,
                "is_ancestor": sibling == entity,
            }
            if data["is_current"] or data["is_ancestor"]:
                tier.insert(0, data)
            else:
                tier.append(data)
        graph.append(tier)
        entity, old = R.entity_supertype.get(entity), entity
    return reversed(graph)


def get_node_colour(n):
    if R.entity_supertype.get(n) is None:
        return "gray"

    def is_relationship(ty=n):
        if ty == "IfcRelationship":
            return True
        ty = R.entity_supertype.get(ty)
        if ty:
            return is_relationship(ty)
        return False

    return "yellow" if is_relationship() else "dodgerblue"


def transform_graph(current_entity, graph_data, only_urls=False):
    graphs = pydot.graph_from_dot_data(graph_data)

    # collect all node names to see if we need to insert args in cluster

    all_nodes = set()

    def collect_nodes(g):
        all_nodes.update(n.get_name() for n in g.get_nodes())
        for sg in g.get_subgraphs():
            collect_nodes(sg)

    for graph in graphs:
        collect_nodes(graph)

    # now visit graph and decorate nodes

    def visit_graph(g):
        names_seen = {}

        edge_nodes_in_cluster = set()

        for e in g.get_edges():
            edge_nodes_in_cluster.add(e.get_source())
            edge_nodes_in_cluster.add(e.get_destination())

        # add nodes to cluster that aren't explicitly declared
        # in the graph
        for n in edge_nodes_in_cluster - all_nodes:
            g.add_node(pydot.Node(n))

        for n in list(g.get_nodes()):
            nm = n.get_label() or n.get_name()

            if nm == '"\\n"':
                # not sure where this comes from, some artefact
                # of the pydot parsing, but it can't be reproduced
                # consistently
                g.del_node(n)
                continue

            if nm in {"graph", "edge", "node"}:
                continue

            if not only_urls:

                if n.get_name() in names_seen:
                    # rank=same groupings otherwise cause
                    # node names to be listed twice
                    args = names_seen[n.get_name()]

                else:
                    args = {"fillcolor": get_node_colour(nm), "shape": "box", "style": "filled"}

                    if n.get_name() == current_entity:
                        args["color"] = "red"

                    names_seen[n.get_name()] = args

                for kv in args.items():
                    n.set(*kv)

            if nm.startswith("Ifc"):
                n.set("URL", url_for("resource", resource=nm, _external=True))

        for sg in g.get_subgraphs():
            visit_graph(sg)

    for graph in graphs:
        visit_graph(graph)

    return graph.to_string()


def process_graphviz(current_entity, md):
    def is_figure(s):
        if "dot_figure" in s:
            return 1
        elif "dot_inheritance" in s:
            return 2
        else:
            return 0

    graphviz_code = filter(is_figure, re.findall("```(.*?)```", md, re.S))

    for c in graphviz_code:
        hash = hashlib.sha256(c.encode("utf-8")).hexdigest()
        fn = os.path.join("svgs", current_entity + "_" + hash + ".dot")
        c2 = transform_graph(current_entity, c, only_urls=is_figure(c) == 2)
        with open(fn, "w") as f:
            f.write(c2)
        md = md.replace("```%s```" % c, "![](/svgs/%s_%s.svg)" % (current_entity, hash))
        subprocess.call([shutil.which("dot") or "dot", "-O", "-Tsvg", "-Gbgcolor=#ffffff00", fn])

    return md


def create_entity_definition(e, bindings):

    # unique name (postfix for multiple occurences, can have template bindings)
    EE = e

    # schema name, updated when traversing supertypes
    e = e.split("_")[0]

    # schema name, constant
    E = e

    table = []

    bindings_seen = set()

    while e:
        keys = [x for x in R.entity_attributes.keys() if x.startswith(e + ".")]
        for k, (is_fwd, ty) in list(zip(keys, map(R.entity_attributes.__getitem__, keys)))[::-1]:
            nm = k.split(".")[1]

            card = re.findall(r"(\[.+?\])", ty)

            if card:
                card = card[0]
            elif is_fwd:
                card = "[0:1]" if "OPTIONAL" in ty else "[1:1]"
            else:
                # default inverse cardinality
                card = "[1:1]"

            bnd = bindings.get((EE, nm), "")
            table.append((nm, card, 2 if bnd else 0))
            if bnd:
                bindings_seen.add((EE, nm))
                table.append((bnd, "", 3))

        e = R.entity_supertype.get(e)

    is_first = True
    for (ent, attr), bnd in bindings.items():
        if ent != EE:
            continue
        if (ent, attr) in bindings_seen:
            continue

        if is_first:
            table.insert(0, ("...", "", 0))
        table.insert(0, (bnd, "", 3))
        table.insert(0, (attr, "", 2))

        is_first = False

    table.append((E, "", 1))
    table = table[::-1]

    table = '<<table border="1" cellborder="0" cellspacing="0" cellpadding="3px">%s</table>>' % "".join(
        "<tr>%s</tr>"
        % "".join(
            '<td width="%d" height="%d" bgcolor="%s" align="left" port="%s%d">%s%s%s</td>'
            % (
                [20, 250][i == 0],
                [24, 18][r[2] == 3],
                ["white", "#cccccc", "#8dc0f4", "#8dc0f4"][r[2]],
                r[0],
                i,
                "<b>" if r[2] == 3 and c else "",
                c,
                "</b>" if r[2] == 3 and c else "",
            )
            for i, c in enumerate(r[:-1])
        )
        for r in table
    )

    return table


def process_graphviz_concept(name, md):
    graphviz_code = filter(lambda s: s.strip().startswith("concept"), re.findall("```(.*?)```", md, re.S))

    for c in graphviz_code:

        hash = hashlib.sha256(c.encode("utf-8")).hexdigest()
        fn = os.path.join("svgs", name + "_" + hash + ".dot")
        c2 = c.replace("concept", "digraph")  # transform_graph(current_entity, c, only_urls=is_figure(c) == 2)

        c2 = re.sub("(?<=\w)\-(?=\w)", "", c2)

        nodes = set(n.split(":")[0] for n in (re.findall("([\:\w]+)\s*\->", c2) + re.findall("\->\s*([\:\w]+)", c2)))

        c2 = re.sub(r"(\w+)\:(\w+)\s*\->\s*([\:\w]+)", lambda m: f"{m.group(1)}:{m.group(2)}1 -> {m.group(3)}", c2)
        c2 = re.sub(r"([\w\:]+)\s*\->\s*(\w+)\:(\w+)", lambda m: f"{m.group(1)} -> {m.group(2)}:{m.group(3)}0", c2)

        bindings = {}
        for ent, attr, bind in re.findall(r'(\w+)\:(\w+)\[binding="([\w_]+)"\]', c2):
            bindings[(ent, attr)] = bind
        c2 = re.sub(r'\w+\:\w+\[binding="[\w_]+"\]', "", c2)

        G = pydot.graph_from_dot_data(c2)[0]

        G.set_node_defaults(shape="plaintext", width="3")
        G.set_nodesep("0.1")
        G.set_splines("polyline")
        G.set_rankdir("LR")

        for n in nodes:
            if n.startswith("Ifc"):
                G.add_node(pydot.Node(n, label=create_entity_definition(n, bindings)))
            elif n.startswith("constraint_"):
                G.get_node(n)[0].set_fillcolor("#ffaaaa")
                G.get_node(n)[0].set_shape("rect")
                G.get_node(n)[0].set_style("filled")
            else:
                G.add_node(pydot.Node(n, label=n.replace("_", " "), fillcolor="#aaffaa", shape="rect", style="filled"))

        # this is ugly, but the node defaults need to come before the edges
        G.obj_dict["nodes"]["node"][0]["sequence"] = -1

        c3 = G.to_string()

        with open(fn, "w") as f:
            f.write(c3)
        md = md.replace("```%s```" % c, "![](/svgs/%s_%s.svg)" % (name, hash))

        subprocess.call([shutil.which("dot") or "dot", "-O", "-Tsvg", "-Gbgcolor=#ffffff00", fn])

    return md


def get_applicable_relationships(usage, concept, resource):
    rows = copy.deepcopy(R.xmi_concepts[usage].get(concept, []))
    rows = [r for r in rows if r.get("ApplicableEntity") == resource]
    if not rows:
        return
    if len(rows[0].keys()) == 1:
        # There must be at least one key which defines the ApplicableEntity
        # In this case, there is no interesting information to display
        return
    data = []
    for row in rows:
        del row["ApplicableEntity"]
        data.append({"predefined_type": row.pop("PredefinedType", None), "name": list(row.values())[0]})
    return data


def separate_camel(s):
    return " ".join(re.split("(?=[A-Z])", s)[1:])


@app.route(make_url("figures/<fig>"))
def get_figure(fig):
    return send_from_directory(os.path.join(REPO_DIR, "docs/figures"), fig)


@app.route(make_url("assets/<path:asset>"))
def get_asset(asset):
    return send_from_directory(os.path.join(REPO_DIR, "docs", "assets"), asset)


@app.route(make_url("examples/<path:example>"))
def get_example(example):
    return send_from_directory(os.path.join(REPO_DIR, "..", "examples", "IFC 4.3"), example)


DOC_ANNOTATION_PATTERN = re.compile(r"\{\s*\..+?\}")


class resource_documentation_builder:
    def __init__(self, resource):
        self.resource = resource
        self.md = get_resource_path(resource)

    @property
    def markdown(self):
        with open(self.md, "r", encoding="utf-8") as f:
            return re.sub(DOC_ANNOTATION_PATTERN, "", "\n".join(f.readlines()[2:]))

    def get_markdown_content(self, heading):
        attrs = []
        fwd_attrs = []

        ty = self.resource
        while ty:
            md_ty_fn = get_resource_path(ty)

            try:
                md_ty = re.sub(DOC_ANNOTATION_PATTERN, "", open(md_ty_fn, encoding="utf-8").read())
            except:
                # @todo
                ty = R.entity_supertype.get(ty)
                continue

            try:
                ty_attrs = list(mdp.markdown_attribute_parser(md_ty, heading))
            except:
                # @todo change markdown parser
                ty = R.entity_supertype.get(ty)
                continue

            if heading == "Attributes":
                ty_attr_di = dict(ty_attrs)
                for a in [k.split(".")[1] for k in R.entity_attributes.keys() if k.startswith(f"{ty}.")][::-1]:
                    b = ty_attr_di.get(a, "")
                    is_fwd, attr_ty = R.entity_attributes[".".join((ty, a))]
                    content = re.sub("\\b_(\\w+?)_\\b", lambda m: m.group(1), b.strip())
                    attrs.append((ty, a, attr_ty, content))
                    if is_fwd:
                        fwd_attrs.append(a)
            else:
                for a, b in ty_attrs[::-1]:
                    # remove underscored words:
                    content = re.sub("\\b_(\\w+?)_\\b", lambda m: m.group(1), b.strip())
                    attrs.append((ty, a, content))
            ty = R.entity_supertype.get(ty)

        attrs = attrs[::-1]

        if heading == "Attributes":
            # Decorate with attribute index
            attr_index = {b: a for a, b in enumerate(fwd_attrs[::-1], 1)}
            attrs = [(a, attr_index.get(b, ""), b, c, d) for a, b, c, d in attrs]

        return attrs

    @property
    def attributes(self):
        return self.get_markdown_content("Attributes")

    @property
    def formal_propositions(self):
        return self.get_markdown_content("Formal Propositions")

    @property
    def concepts(self):
        return self.get_markdown_content("Concepts")


@app.route("/api/v0/resource/<resource>")
def api_resource(resource):
    b = resource_documentation_builder(resource)
    if b.attributes is None:
        abort(404)
    definition = b.markdown
    if "\n\n" in definition:
        definition = definition[0 : definition.index("\n\n")]
    definition = markdown.markdown(definition)
    attributes = [a[1:] for a in b.attributes]
    return jsonify({"resource": resource, "definition": definition, "attributes": attributes})


@app.route(make_url("property/<prop>.htm"))
def property(prop):
    prop = "".join(c for c in prop if c.isalnum())
    md = os.path.join(REPO_DIR, "docs", "properties", prop[0].lower(), prop + ".md")
    try:
        mdc = open(md, "r", encoding="utf-8").read()
    except:
        mdc = ""

    idx = ""
    mdc = re.sub(DOC_ANNOTATION_PATTERN, "", mdc)

    psets = [[pset] for pset, pdef in R.pset_definitions.items() if any(p["name"] == prop for p in pdef["properties"])]

    html = process_markdown(prop, mdc)

    html += tabulate.tabulate(psets, headers=["Referenced in"], tablefmt="html")

    return render_template(
        "property.html",
        base=base,
        navigation=get_navigation(),
        content=html,
        number=idx,
        entity=prop,
        path=md[len(REPO_DIR) + 1 :].replace("\\", "/"),
    )


def process_markdown(resource, mdc, as_attribute=False):
    html = markdown.markdown(process_graphviz(resource, mdc), extensions=["tables", "fenced_code"])

    soup = BeautifulSoup(html)

    # First h1 is handled by the template
    try:
        soup.find("h1").decompose()
    except:
        # only entities have H1?
        pass

    if as_attribute:
        return str(soup.text)

    # Change svg img references to embedded svg because otherwise URLS are not interactive
    for img in soup.findAll("img"):
        if img["src"].endswith(".svg"):
            entity, hash = img["src"].split("/")[-1].split(".")[0].split("_")
            svg = BeautifulSoup(open(os.path.join("svgs", entity + "_" + hash + ".dot.svg")))
            img.replaceWith(svg.find("svg"))
            img = svg
        elif img["src"].startswith("http"):
            pass
        else:
            img["src"] = img["src"][9:]

    # Tag all special notes separately. In markdown they are all lumped in a single block quote.
    for blockquote in soup.findAll("blockquote"):
        has_aside = False
        for p in blockquote.findAll("p"):
            try:
                keyword, contents = p.text.split(" ", 1)
            except:
                continue
            valid_keywords = ["HISTORY", "IFC", "EXAMPLE", "NOTE"]
            has_valid_keyword = False
            for valid_keyword in valid_keywords:
                if valid_keyword in keyword:
                    has_valid_keyword = True
                    break
            if not has_valid_keyword:
                continue
            has_aside = True
            aside = soup.new_tag("aside")
            if keyword.startswith("IFC"):
                # This is typically something like "IFC4 CHANGE" denoting a historic change reason
                keyword, keyword2, contents = p.text.split(" ", 2)
                keyword = "-".join((keyword, keyword2))
            keyword = keyword.strip()
            css_class = keyword.lower()
            if "addendum" in css_class or "change" in css_class:
                css_class = "change"
            if "deprecation" in css_class:
                css_class = "deprecation"
            aside["class"] = f"aside-{css_class}"
            mark = soup.new_tag("mark")
            mark.string = keyword
            aside.string = contents
            aside.insert(0, mark)
            blockquote.insert_before(aside)
            p.decompose()
        if has_aside:
            blockquote.decompose()

    html = str(soup).replace("{{ base }}", base)

    return html


@app.route(make_url("lexical/<resource>.htm"))
def resource(resource):
    try:
        idx = name_to_number()[resource]
    except:
        abort(404)

    SectionNumberGenerator.set(idx)
    SectionNumberGenerator.begin_subsection()

    definition_number = SectionNumberGenerator.generate()

    html = ""

    md = get_resource_path(resource, abort_on_error=False)

    attribute_table = ""

    try:
        mdc = open(md, "r", encoding="utf-8").read()
    except:
        mdc = ""

    mdc = re.sub(DOC_ANNOTATION_PATTERN, "", mdc)

    if "Entities" in md:
        builder = resource_documentation_builder(resource)
        return render_template(
            "entity.html",
            base=base,
            navigation=get_navigation(resource),
            number=idx,
            definition_number=definition_number,
            definition=get_definition(resource, mdc),
            entity=resource,
            path=md[len(REPO_DIR) :].replace("\\", "/"),
            entity_inheritance=get_entity_inheritance(resource),
            attributes=get_attributes(resource, builder),
            formal_propositions=get_formal_propositions(resource, builder),
            property_sets=get_property_sets(resource, builder),
            concept_usage=get_concept_usage(resource, builder),
            examples=get_examples(resource),
            adoption=get_adoption(resource),
            formal_representation=get_formal_representation(resource),
            changelog=get_changelog(resource),
            is_deprecated=resource in R.deprecated_entities,
            is_abstract=resource in R.abstract_entities,
        )
    elif resource in R.pset_definitions.keys():
        return render_template(
            "property.html",
            base=base,
            navigation=get_navigation(resource),
            content=process_markdown(resource, mdc),
            number=idx,
            definition_number=definition_number,
            entity=resource,
            path=md[len(REPO_DIR) :].replace("\\", "/"),
            applicability=get_applicability(resource),
            properties=get_properties(resource),
            changelog=get_changelog(resource),
        )
    builder = resource_documentation_builder(resource)
    return render_template(
        "type.html",
        base=base,
        navigation=get_navigation(resource),
        content=get_definition(resource, mdc),
        number=idx,
        definition_number=definition_number,
        entity=resource,
        path=md[len(REPO_DIR) :].replace("\\", "/"),
        type_values=get_type_values(resource, mdc),
        formal_propositions=get_formal_propositions(resource, builder),
        formal_representation=get_formal_representation(resource),
        changelog=get_changelog(resource),
    )


def get_type_values(resource, mdc):
    values = R.type_values.get(resource)
    if not values:
        return
    has_description = values[0] == values[0].upper()
    if has_description:
        soup = BeautifulSoup(process_markdown(resource, mdc))
        described_values = []
        for value in values:
            description = None
            for h in soup.findAll("h3"):
                if h.text != value:
                    continue
                description = BeautifulSoup()
                for sibling in h.find_next_siblings():
                    if sibling.name == "h3":
                        break
                    description.append(sibling)
                description = str(description)
            described_values.append({"name": value, "description": description})
        values = described_values
    return {"number": SectionNumberGenerator.generate(), "has_description": has_description, "schema_values": values}


def get_definition(resource, mdc):
    # Only match up to the first header
    if "## " in mdc:
        mdc = mdc[0 : mdc.index("## ")]
    return process_markdown(resource, mdc)


def get_applicability(resource):
    return {"number": SectionNumberGenerator.generate(), "entities": R.pset_definitions[resource]["applicability"]}


def get_properties(resource):
    def make_prop(prop):
        try:
            doc = process_markdown(
                resource,
                open(
                    os.path.join(REPO_DIR, "docs/properties/%s/%s.md") % (prop["name"][0].lower(), prop["name"])
                ).read(),
                as_attribute=True,
            )
        except:
            doc = "<i>Missing property definition</i>"

        if R.pset_definitions[resource]["kind"] == "quantity_set":
            prop_type = []
        else:
            prop_type = [prop["type"]]

        return [
            prop["name"],
            *prop_type,
            prop["data"],
            doc
            + f"<a class='button' href='{make_url('property/'+prop['name'])}.htm' style='padding:0;margin:0 0.5em'><span class='icon-edit'></span></a>",
        ]

    attrs = list(map(make_prop, R.pset_definitions[resource]["properties"]))

    headers = ("Name", "Property Type", "Data Type", "Definition")
    if R.pset_definitions[resource]["kind"] == "quantity_set":
        # Quantity sets elements are always a singular type, as opposed to
        # property set items which are composed of a property type (single,
        # bounded, ...) and a data type.
        headers = (headers[0],) + headers[2:]

    return {
        "number": SectionNumberGenerator.generate(),
        "table": tabulate.tabulate(attrs, headers=headers, tablefmt="unsafehtml"),
    }


def get_attributes(resource, builder):
    if not builder:
        return
    attrs = builder.attributes
    supertype_counts = Counter()
    supertype_counts.update([a[0] for a in attrs])
    attrs = [a[1:] for a in attrs]
    supertype_counts = list(supertype_counts.items())[::-1]
    insertion_points = [0] + list(itertools.accumulate(map(operator.itemgetter(1), supertype_counts[::-1])))[:-1]
    group_data = supertype_counts[::-1]

    results = []
    for i, attr in enumerate(attrs):
        if i in insertion_points:
            name, total_attributes = group_data[insertion_points.index(i)]
            group = {
                "name": name,
                "attributes": [],
                "is_inherited": insertion_points[-1] != i,
                "total_attributes": total_attributes,
            }
            results.append(group)
        group["attributes"].append(
            {
                "number": attr[0],
                "name": attr[1],
                "type": attr[2],
                "description": process_markdown(resource, attr[3]),
                "is_inverse": not attr[0],
            }
        )

    return {
        "number": SectionNumberGenerator.generate(),
        "groups": results,
    }


def get_formal_propositions(resource, builder):
    if not builder:
        return

    defs = {k[1]: k[2] for k in builder.formal_propositions}
    clauses = R.entity_where_clauses.get(resource, [])

    if not clauses:
        return

    return {
        "number": SectionNumberGenerator.generate(),
        "items": [
            {"name": c[0], "formal": c[1], "description": process_markdown(resource, defs.get(c[0]))} for c in clauses
        ],
    }


def get_entity_inheritance(resource):
    try:
        return {
            "number": SectionNumberGenerator.generate(),
            "graph": get_inheritance_graph(resource),
        }
    except:
        import traceback

        traceback.print_exc()


def get_property_sets(resource, builder):
    concepts = list(builder.concepts)
    psets = []
    for concept in concepts:
        name = get_concept_name(concept[1])
        if "Property Sets" not in name and "Quantity Sets" not in name:
            continue
        usage = get_usage_name(name)
        stripped_name = name.replace(" ", "")
        relationships = get_applicable_relationships(usage, stripped_name, concept[0])
        for pset in relationships or []:
            properties = R.pset_definitions[pset["name"]]["properties"]
            pset["properties"] = [p["name"] for p in properties]
            psets.append(pset)

    if psets:
        return {
            "number": SectionNumberGenerator.generate(),
            "psets": sorted(psets, key=lambda x: x["name"]),
        }


def get_concept_name(name):
    if isinstance(name, tuple):
        return name[1]
    return name


def get_usage_name(name):
    name = name.replace(" ", "")
    for view_name, concepts in R.xmi_concepts.items():
        if name in concepts:
            return view_name
    return "GeneralUsage"


def get_concept_usage(resource, builder):
    ty = resource
    supertype_chain = []
    while ty is not None:
        supertype_chain.append(ty)
        ty = R.entity_supertype.get(ty)

    concepts = list(builder.concepts)

    # Create a lookup for concept name to URL
    concept_hierarchy = make_concept([""])

    def flatten_hierarchy(h):
        yield h
        for ch in h.children:
            yield from flatten_hierarchy(ch)

    concept_lookup = {c.text.replace(" ", ""): (c.text, c.url) for c in flatten_hierarchy(concept_hierarchy)}

    groups = []
    for concept in concepts:
        if not groups or groups[-1]["name"] != concept[0]:
            groups.append(
                {
                    "name": concept[0],
                    "is_inherited": concept[0] != resource,
                    "concepts": [],
                }
            )
        name = get_concept_name(concept[1])
        usage = get_usage_name(name)
        stripped_name = name.replace(" ", "")
        data = {
            "name": name,
            "description": process_markdown(resource, concept[2]),
            "usage": separate_camel(usage).replace("General Usage", "General"),
            "url": concept_lookup.get(stripped_name, [None, None])[1],
            "applicable_relationships": get_applicable_relationships(usage, stripped_name, groups[-1]["name"]),
        }
        groups[-1]["concepts"].append(data)

    if groups:
        return {
            "number": SectionNumberGenerator.generate(),
            "groups": groups,
        }


def get_examples(resource):
    examples = []
    for name in R.examples_by_type.get(resource.upper()) or []:
        examples.append({
            "name": name,
            "url": url_for("annex_e_example_page", s=name),
            "image": url_for("get_example", example=name) + "/thumb.png"
        })
    if examples:
        return {"number": SectionNumberGenerator.generate(), "examples": examples}


def get_adoption(resource):
    return # Is the industry ready? :)
    import random
    # Just a stub: inspiration from https://caniuse.com/css-grid
    # ... and so many other implementation matrixes online
    softwares = []
    for i in range(0, random.randint(2, 10)):
        versions = []
        for j in range(0, random.randint(1, 5)):
            support = "not-supported"
            if j > 2 or random.randint(0, 1) == 1:
                support = "supported"
            elif j > 0:
                support = "partially-supported"
            versions.append({
                "name": f"V1.{j}",
                "support": support
            })
        softwares.append({ "name": f"Software {i+1}", "versions": reversed(versions) })
    return {"number": SectionNumberGenerator.generate(), "softwares": softwares}

def get_formal_representation(resource):
    express = R.entity_definitions.get(resource)
    if express:
        return {"number": SectionNumberGenerator.generate(), "express": express}


def get_changelog(resource):
    changelog_data = R.changes_by_type.get(resource, {})
    if not changelog_data:
        return
    changelog = {"number": SectionNumberGenerator.generate(), "sections": []}
    SectionNumberGenerator.begin_subsection()
    for section, changes in changelog_data.items():
        changelog["sections"].append(
            {
                "name": section,
                "number": SectionNumberGenerator.generate(),
                "changes": [
                    {
                        "is_addition": "add" in c[0],
                        "is_deletion": "delet" in c[0],
                        "is_modification": "modif" in c[0],
                        "what_changed": c[1],
                        "description": c[2],
                    }
                    for c in changes
                ],
            }
        )
    SectionNumberGenerator.end_subsection()
    return changelog


class FigureNumberer:
    index = {}

    @classmethod
    def clear(cls):
        cls.index = {}

    @classmethod
    def generate(cls, figure, number):
        previous_header = None
        previous = figure
        while not previous_header:
            previous = previous.find_previous()
            if not previous:
                break
            elif previous.name.lower().startswith("h"):
                previous_header = previous
                break

        if previous_header:
            parent_number = previous_header.contents[0].strip().split(" ", 1)[0]
            alphabet = "A"
            generated_number = parent_number + "." + alphabet
            while generated_number in cls.index.values():
                alphabet = chr(ord(alphabet) + 1)
                generated_number = parent_number + "." + alphabet
            cls.index[number] = generated_number

    @classmethod
    def replace_references(cls, html):
        for placeholder_number, generated_number in cls.index.items():
            html = html.replace(f"Figure {placeholder_number}", f"Figure {generated_number}")
            html = html.replace(f"Figure-{placeholder_number}", f"Figure-{generated_number}")
            html = html.replace(f"Table {placeholder_number}", f"Table {generated_number}")
            html = html.replace(f"Table-{placeholder_number}", f"Table-{generated_number}")
        return html


class SectionNumberGenerator:
    number = "1"

    @classmethod
    def set(cls, number):
        cls.number = number

    @classmethod
    def generate(cls):
        numbers = cls.number.split(".")
        numbers[-1] = str(int(numbers[-1]) + 1)
        cls.number = ".".join(numbers)
        return cls.number

    @classmethod
    def begin_subsection(cls):
        cls.number += ".0"

    @classmethod
    def end_subsection(cls):
        cls.number = ".".join(cls.number.split(".")[0:-1])


@app.route(make_url("annex-b.html"))
def annex_b():
    items = [
        {"number": "B.1", "title": "Entities", "url": make_url("annex-b1.html")},
        {"number": "B.2", "title": "Property sets", "url": make_url("annex-b2.html")},
        {"number": "B.3", "title": "Properties", "url": make_url("annex-b3.html")},
    ]
    return render_template("annex-b.html", base=base, navigation=get_navigation(), items=items)


@app.route(make_url("annex-b1.html"))
def annex_b1():
    items = [
        {"number": name_to_number()[n], "url": url_for("resource", resource=n), "title": n}
        for n in sorted(entity_names() + type_names())
    ]
    return render_template("annex-b.html", base=base, navigation=get_navigation(), items=items, is_dictionary=True)


@app.route(make_url("annex-b2.html"))
def annex_b2():
    items = [
        {"number": name_to_number()[n], "url": url_for("resource", resource=n), "title": n}
        for n in sorted(R.pset_definitions.keys())
        if n in name_to_number()
    ]
    return render_template("annex-b.html", base=base, navigation=get_navigation(), items=items, is_dictionary=True)


@app.route(make_url("annex-b3.html"))
def annex_b3():
    items = [
        {"number": "", "url": url_for("property", prop=n), "title": n}
        for n in sorted(set([p["name"] for pdef in R.pset_definitions.values() for p in pdef["properties"]]))
    ]
    return render_template("annex-b.html", base=base, navigation=get_navigation(), items=items)


def make_concept(path, number_path=None):
    md_root = os.path.join(REPO_DIR, "docs/templates")

    if number_path is None:
        number_path = "4"

    children = enumerate(
        sorted(
            [
                d
                for d in os.listdir(os.path.join(md_root, *path))
                if os.path.exists(os.path.join(md_root, *path, d, "README.md"))
            ]
        ),
        1,
    )
    return toc_entry(
        url=make_url("concepts/" + "/".join(p for p in path if p).replace(" ", "_") + "/content.html"),
        number=number_path,
        text=path[-1],
        children=[make_concept(path + [c], number_path=f"{number_path}.{i}") for i, c in children],
    )


def create_concept_table(view_name, xmi_concept, types=None):
    rows = R.xmi_concepts[view_name][xmi_concept]
    bindings = [("ApplicableEntity", ("", ""))] + list(
        parse_bindings(os.path.join(REPO_DIR, "schemas/IFC.xml"), xmi_concept)
    )
    bound_keys = set(sum([list(r.keys()) for r in rows], []))
    bound_keys = [a[0] for a in bindings if a[0] in bound_keys]
    headers = [f"{a}<br>{b}{'.' if b else ''}{c}" for a, (b, c) in bindings if a in bound_keys]
    if types is not None:
        rows = [r for r in rows if r.get("ApplicableEntity") in types]
    rows = [[r.get(k, "") for k in bound_keys] for r in rows]
    return headers, rows


@app.route(make_url("concepts/content.html"))
def concept_list():
    fn = os.path.join(REPO_DIR, "docs", "templates", "README.md")
    html = process_markdown("", open(fn).read())
    return render_template(
        "chapter.html",
        base=base,
        navigation=get_navigation(),
        content=html,
        path=fn[len(REPO_DIR) :].replace("\\", "/"),
        title=chapter_lookup(number=4).get("name"),
        number=4,
        subs=make_concept([""]).children,
    )


@app.route(make_url("concepts/<path:s>/content.html"))
def concept(s=""):
    md_root = os.path.join(REPO_DIR, "docs/templates")

    s = s.replace("_", " ")

    n = "4"
    if s:
        ps = s.split("/")
        t = ps[-1]
        for pt in itertools.accumulate([[p] for p in ps]):
            n += ".%d" % (sorted(os.listdir(os.path.join(md_root, *pt[:-1]))).index(pt[-1]) + 1)
    else:
        t = chapter_lookup(number=4).get("name")

    fn = os.path.join(md_root, s, "README.md")

    if os.path.exists(fn):
        html = markdown.markdown(process_graphviz_concept("".join(c for c in s if c.isalnum()), open(fn).read()))
        soup = BeautifulSoup(html)

        # First h1 is handled by the template
        h1 = soup.find("h1")
        if h1 is not None:
            h1.decompose()

        # Change svg img references to embedded svg
        # because otherwise URLS are not interactive
        for img in soup.findAll("img"):
            if img["src"].endswith(".svg"):
                entity, hash = img["src"].split("/")[-1].split(".")[0].split("_")
                svg = BeautifulSoup(open(os.path.join("svgs", entity + "_" + hash + ".dot.svg")))
                svg_node = svg.find("svg")
                svg_node.attrs["width"] = "%dpx" % (int(svg_node.attrs["width"][0:-2]) // 4 * 3)
                svg_node.attrs["height"] = "%dpx" % (int(svg_node.attrs["height"][0:-2]) // 4 * 3)
                img.replaceWith(svg_node)
            else:
                img["src"] = img["src"][9:]

        html = str(soup)
    else:
        html = ""

    xmi_concept = t.replace(" ", "")

    for view_name, concepts in R.xmi_concepts.items():
        if xmi_concept in concepts:
            html += f"<h3>{separate_camel(view_name)}</h3>"
            headers, rows = create_concept_table(view_name, xmi_concept, None)
            if rows:
                html += tabulate.tabulate(rows, headers=headers, tablefmt="unsafehtml")

    subs = make_concept(s.split("/")).children

    return render_template(
        "concept.html",
        base=base,
        navigation=get_navigation(resource, number=n),
        content=html,
        path=fn[len(REPO_DIR) :].replace("\\", "/"),
        title=t,
        number=n,
        subs=subs,
    )


@app.route(make_url("chapter-<n>/"))
def chapter(n):
    try:
        n = int(n)
    except:
        abort(404)

    chp = chapter_lookup(number=n)
    t = chp.get("name")
    md_root = os.path.join(REPO_DIR, "docs/schemas")
    cat = t.split(" ")[0].lower()

    fn = os.path.join(md_root, cat, "README.md")

    if os.path.exists(fn):
        html = markdown.markdown(open(fn).read())
        soup = BeautifulSoup(html)
        # First h1 is handled by the template
        soup.find("h1").decompose()
        html = str(soup)
    else:
        html = ""

    subs = [itms for t, itms in R.hierarchy if t == chp.get("name")][0]

    def get_entry(pair):
        i, text = pair
        return toc_entry(text, url=url_for("schema", name=text.lower()), number=f"{n}.{i}")

    subs = list(map(get_entry, enumerate(map(operator.itemgetter(0), subs), 1)))

    return render_template(
        "chapter.html",
        base=base,
        navigation=get_navigation(number=n),
        content=html,
        path=fn[len(REPO_DIR) :].replace("\\", "/"),
        title=t,
        number=n,
        subs=subs,
    )


@app.route("/")
def cover(s="cover"):
    fn = os.path.join(REPO_DIR, "content", "cover.md")
    title = navigation[1][0]["name"]
    return render_template(
        "cover.html",
        base=base,
        navigation=get_navigation(),
        content=markdown.markdown(render_template_string(open(fn).read(), base=base)),
        path=fn[len(REPO_DIR) :].replace("\\", "/"),
        subs=[],
    )


@app.route(make_url("content/<s>.htm"))
def content(s="cover"):
    fn = os.path.join(REPO_DIR, "content")
    fn = os.path.join(fn, s + ".md")

    if not os.path.exists(fn):
        abort(404)

    try:
        i = content_names.index(s)
        number = i + 1
        title = navigation[1][i]["name"]
    except:

        try:
            i = content_names_2.index(s)
            number = ""
            title = s[0].upper() + s[1:]
        except:
            abort(404)

    html = process_markdown("", render_template_string(open(fn).read(), base=base))
    return render_template(
        "static.html",
        base=base,
        navigation=get_navigation(),
        content=html,
        path=fn[len(REPO_DIR) :].replace("\\", "/"),
        title=title,
        number=number,
    )


@app.route(make_url("annex-a.html"))
def annex_a():
    return render_template("annex-a.html", base=base, navigation=get_navigation())


def annotate_hierarchy(data=None, start=1, number_path=None):
    level_2_headings = ("Schema Definition", "Types", "Entities", "Property Sets", "Functions", "Rules")

    def items(d):
        if len(number_path or []) == 2:
            return [(h, dict(d).get(h, [])) for h in level_2_headings]
        elif isinstance(d, dict):
            return d.items()
        else:
            return [(x, []) if isinstance(x, str) else x for x in d]

    def get_url(idx, text):
        if len(number_path) == 0:
            return make_url("chapter-%d/" % idx)
        elif len(number_path) == 1:
            return url_for("schema", name=text.lower())
        elif len(number_path) == 2:
            fragment = (".".join(list(map(operator.itemgetter(0), number_path)) + [str(idx)]) + "-" + text).replace(
                " ", "-"
            )
            return url_for("schema", name=number_path[1][1].lower()) + f"#{fragment}"
        elif len(number_path) == 3:
            return url_for("resource", resource=text)

    if data is None:
        data = R.hierarchy

    if number_path is None:
        number_path = []

    return [
        toc_entry(
            text=k,
            number=".".join(list(map(operator.itemgetter(0), number_path)) + [str(i)]),
            url=get_url(i, k),
            children=annotate_hierarchy(data=vs, number_path=number_path + [(str(i), k)]),
        )
        for i, (k, vs) in enumerate(items(data), start)
    ]


@app.route(make_url("toc.html"))
def toc():
    subs = navigation[1][0:4]
    subs += annotate_hierarchy(start=5)
    return render_template("chapter.html", base=base, navigation=get_navigation(), title="Contents", subs=subs)


@app.route(make_url("annex-c.html"))
def annex_c():
    entities = []
    indentation_map = {0: entities}
    with open("inheritance_listing.txt") as inheritance_listings:
        for line in inheritance_listings:
            line = line.strip("\n")
            padding = line.count(" ")
            entity = line.strip()
            data = {
                "number": name_to_number()[entity],
                "url": url_for("resource", resource=entity),
                "name": entity,
                "children": [],
            }
            if padding == 0:
                entities.append(data)
            else:
                indentation_map[padding - 1]["children"].append(data)
            indentation_map[padding] = data

    return render_template("annex-c.html", base=base, navigation=get_navigation(), entities=entities)


@app.route(make_url("annex-d.html"))
def annex_d():
    diagrams = map(os.path.basename, glob.glob(os.path.join(REPO_DIR, "output/IFC.xml/*.png")))
    diagrams = [
        toc_entry(s[:-4], url=url_for("annex_d_diagram_page", s=s[:-4]), number="D-%d" % i)
        for i, s in enumerate(sorted(diagrams), start=1)
    ]
    return render_template("annex-d.html", base=base, navigation=get_navigation(), diagrams=diagrams)


@app.route(make_url("annex_d/<s>.html"))
def annex_d_diagram_page(s):
    return render_template("annex-d-item.html", base=base, navigation=get_navigation(), name=s)


@app.route(make_url("annex_d/<s>.png"))
def annex_d_diagram(s):
    return send_from_directory(os.path.join(REPO_DIR, "output/IFC.xml"), s + ".png")


@app.route(make_url("annex-e.html"))
def annex_e():
    examples = map(os.path.basename, filter(os.path.isdir, glob.glob(os.path.join(REPO_DIR, "../examples/IFC 4.3/*"))))
    examples = sorted(toc_entry(s, url=url_for("annex_e_example_page", s=s)) for s in examples)
    return render_template("annex-e.html", base=base, navigation=get_navigation(), examples=examples)


@app.route(make_url("annex-f.html"))
def annex_f():
    with open("changes_by_schema.json") as f:
        changelog_data = json.load(f)
        changelog = {"sections": []}
        SectionNumberGenerator.begin_subsection()
        for section in changelog_data:
            section_name = section[0]
            changes = section[1]
            changelog["sections"].append(
                {
                    "name": section_name,
                    "changes": [
                        {
                            "entity": c[0],
                            "is_addition": "add" in c[1],
                            "is_deletion": "delet" in c[1],
                            "is_modification": "modif" in c[1],
                            "what_changed": c[2],
                            "description": c[3],
                        }
                        for c in changes
                    ],
                }
            )
        SectionNumberGenerator.end_subsection()
    return render_template("annex-f.html", base=base, navigation=get_navigation(), changelogs=changelog)


@app.route(make_url("annex_e/<s>.html"))
def annex_e_example_page(s):
    subs = map(os.path.basename, filter(os.path.isdir, glob.glob(os.path.join(REPO_DIR, "../examples/IFC 4.3/*"))))
    if s not in subs:
        abort(404)

    fn = glob.glob(os.path.join(REPO_DIR, "../examples/IFC 4.3", s, "*.md"))[0]
    html_raw = process_markdown("", open(fn).read())

    soup = BeautifulSoup(html_raw)

    example_dir = os.path.join(REPO_DIR, "../examples/IFC 4.3", s)

    code = open(
        (
            glob.glob(os.path.join(example_dir, "*.ifc"))
            + glob.glob(os.path.join(example_dir, "*.xml"))
        )[0],
        encoding="ascii",
        errors="ignore",
    ).read()
    path_repo = "buildingSMART/Sample-Test-Files"
    path = fn[len(os.path.join(REPO_DIR, "../examples/")) :]

    # Use regex because globbing is case sensitive
    rule = re.compile(r".*\.(png|jpg|jpeg)", re.IGNORECASE)
    images = [f"{base}/examples/{s}/{name}" for name in os.listdir(example_dir) if rule.match(name)]

    return render_template(
        "annex-e-item.html",
        base=base,
        navigation=get_navigation(),
        content=html_raw,
        path=path,
        repo=path_repo,
        title=s,
        code=code,
        images=images,
    )


@app.route(make_url("<name>/content.html"))
def schema(name):
    md_root = os.path.join(REPO_DIR, "docs/schemas")

    cat_full, schemas = [(t, itms) for t, itms in R.hierarchy if name in [i[0].lower() for i in itms]][0]
    cat = cat_full.split(" ")[0].lower()
    t, subs = [x for x in schemas if x[0].lower() == name][0]
    chp = chapter_lookup(cat=cat)

    n1 = chp.get("number")
    n2 = [s[0] for s in schemas].index(t) + 1
    n = f"{n1}.{n2}"
    fn = os.path.join(md_root, cat, t, "README.md")

    SectionNumberGenerator.set(n)
    SectionNumberGenerator.begin_subsection()

    definition = None
    if os.path.exists(fn):
        definition_number = SectionNumberGenerator.generate()
        definition = process_markdown("", open(fn).read())

    order = ["Types", "Entities", "Property Sets", "Quantity Sets", "Functions", "Rules"]
    categories = [
        toc_entry(
            o,
            number=f"{n}.{ii}",
            children=[
                toc_entry(c, number=f"{n}.{ii}.{jj}", url=url_for("resource", resource=c))
                for jj, c in enumerate(subs.get(o, []), 1)
            ],
        )
        for ii, o in enumerate(order, 2)
    ]

    return render_template(
        "subchapter.html",
        base=base,
        navigation=get_navigation(number=n),
        definition=definition,
        path=fn[len(REPO_DIR) :].replace("\\", "/"),
        title=t,
        number=n,
        subnumber=definition_number,
        categories=categories,
    )


@app.route("/search", methods=["GET", "POST"])
def search():
    matches = []
    query = ""
    if request.args.get("query"):
        solr = pysolr.Solr("http://localhost:8983/solr/ifc")
        query = request.args.get("query")
        results = solr.search("body:(%s)" % query, **{"hl": "on", "hl.fl": "body"})
        h = results.highlighting

        def format(s):
            return re.sub(r"[^\w\s<>/]", "", s)

        def get_url(r):
            if r.get("resourceType", ["resource"]) == ["resource"]:
                return url_for("resource", resource=r["title"][0])
            else:
                return url_for("property", prop=r["title"][0])

        matches = [
            {"url": get_url(r), "match": format(h[r["id"]]["body"][0]), "title": r["title"][0]}
            for r in list(results)[0:10]
        ]

    return render_template("search.html", base=base, navigation=get_navigation(), matches=matches, query=query)


@app.route("/sandcastle", methods=["GET", "POST"])
def sandcastle():

    md = ""
    html = ""

    if request.method == "POST" and request.form["md"]:

        md = request.form["md"]

        html = markdown.markdown(process_graphviz("sandcastle", md), extensions=["tables", "fenced_code"])

        soup = BeautifulSoup(html)

        # Change svg img references to embedded svg
        # because otherwise URLS are not interactive
        for img in soup.findAll("img"):
            if img["src"].endswith(".svg"):
                entity, hash = img["src"].split("/")[-1].split(".")[0].split("_")
                svg = BeautifulSoup(open(os.path.join("svgs", entity + "_" + hash + ".dot.svg")))
                img.replaceWith(svg.find("svg"))

        html = str(soup)

    return render_template("sandcastle.html", base=base, html=html, md=md)


ifcre = re.compile(r"(Ifc|Pset_|Qto_)\w+(?!(.ht|</a|</h|.md| - IFC4.3))")


@app.after_request
def after(response):
    if request.path.endswith(".htm") or request.path.endswith(".html"):
        FigureNumberer.clear()

        html = response.data.decode("utf-8")

        # I know, I know, string to dom to string to dom to ...
        soup = BeautifulSoup(html)

        h1 = soup.findAll("h1")[0]
        title = soup.findAll("title")[0]
        title.string = h1.text + " - " + title.string

        main_content = soup.find_all(id="main-content")
        main_content = main_content[0] if len(main_content) else None

        if main_content:
            for img in main_content.findAll("img"):
                # Capture images as numbered figures
                parent = img.parent
                if parent.name == "a":
                    parent = parent.parent
                parent.name = "figure"
                has_caption = False
                sibling = parent.find_next_sibling()
                if parent.text.strip() and parent.text.strip().startswith("Figure"):
                    # Option 1: the figure caption is in the same block as the image
                    has_caption = True
                    figcaption = soup.new_tag("figcaption")
                    figcaption.string = parent.text
                    extracted_img = img.extract()
                    parent.string = ""
                    parent.append(extracted_img)
                    parent.append(figcaption)
                    FigureNumberer.generate(parent, figcaption.text.split(" ", 2)[1])
                elif sibling and sibling.name == "p" and sibling.text.startswith("Figure"):
                    # Option 2: the figure caption is in the next block
                    has_caption = True
                    figcaption = sibling.extract()
                    figcaption.name = "figcaption"
                    parent.append(figcaption)
                    FigureNumberer.generate(parent, figcaption.text.split(" ", 2)[1])
                elif img.get("title", "").strip():
                    # Option 3: the image has a "title" tag being (ab)used as a caption
                    # Not very nice, as the title in HTML is not the same as the figcaption
                    # This is lazy captioning :)
                    has_caption = True
                    figcaption = soup.new_tag("figcaption")
                    figcaption.string = img["title"].strip()
                    parent.append(figcaption)
                    FigureNumberer.generate(parent, figcaption.text.split(" ", 2)[1])
                if not has_caption:
                    figcaption = soup.new_tag("figcaption")
                    figcaption.string = "Figure " + str(uuid.uuid4())
                    parent.append(figcaption)
                    FigureNumberer.generate(parent, figcaption.text.split(" ", 2)[1])

            for table in main_content.findAll("table"):
                figure = soup.new_tag("figure")
                table.insert_before(figure)
                figure.append(table.extract())
                parent = figure
                has_caption = False

                sibling = parent.find_next_sibling()
                if sibling and sibling.name == "p" and sibling.text.startswith("Table"):
                    has_caption = True
                    figcaption = sibling.extract()
                    figcaption.name = "figcaption"
                    parent.append(figcaption)
                    FigureNumberer.generate(parent, figcaption.text.split(" ", 2)[1])

                if not has_caption:
                    figcaption = soup.new_tag("figcaption")
                    figcaption.string = "Table " + str(uuid.uuid4())
                    parent.append(figcaption)
                    FigureNumberer.generate(parent, figcaption.text.split(" ", 2)[1])

        for element in soup.findAll(["h2", "h3", "h4", "h5", "h6", "figure"]):
            id_element = element

            if element.name == "figure":
                element = element.findChild("figcaption", recursive=False)
                value = element.text.strip()
            else:
                value = element.text.strip()

            anchor_tag = re.sub("[^0-9a-zA-Z.]+", "-", value)

            anchor_id = soup.new_tag("a")
            anchor_id["id"] = anchor_tag
            id_element.insert(0, anchor_id)

            anchor = soup.new_tag("a")
            anchor["href"] = "#" + anchor_tag
            icon = soup.new_tag("i")
            icon["data-feather"] = "link"
            anchor.append(icon)
            element.append(anchor)

        html = FigureNumberer.replace_references(str(soup))

        def decorate_link(m):
            w = m.group(0)
            if w in R.entity_definitions or w in R.pset_definitions:
                return "<a href='" + url_for("resource", resource=w) + "'>" + w + "</a>"
            else:
                return w

        response.data = ifcre.sub(decorate_link, html)

    return response
