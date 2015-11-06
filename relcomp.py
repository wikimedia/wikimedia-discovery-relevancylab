#!/usr/bin/env python

# relcomp.py - generate an HTML report comparing two relevance lab
# query runs
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
# http://www.gnu.org/copyleft/gpl.html

# TODO:
# read info from the .ini file to get names and maybe other info

import argparse
import json
import os
import sys
import textwrap

from abc import ABCMeta, abstractmethod
from itertools import izip_longest
from random import shuffle


class Metric(object):
    """A metric of some sort that we want to keep track of while comparing two
       query runs.

    Attributes:
        name: a string with the name of the metric for printing
        total_queries: number of queries processed by this metric
        baseline_count: number of queries in the baseline satisfying the metric
        delta_count: number of queries in the delta satisfying the metric
        b2d_diff: examples of metric present in baseline, absent in delta
        d2b_diff: examples of metric present in delta, absent in baseline (unsymmetric)
        symmetric: boolean indicating whether metric is symmetric
        printnum: max number of examples to print
        printset: "random" or "ordered"--determines the order of examples printed
        raw_count: should output be raw_count rather than percent
        symbols: mnemonic symbols; [0] used for b2d or symmetric, [1] used for d2b

    Non-symmetric metrics can be true of either the baseline or delta,
        both, or neither. An example is "zero results".

    Symmetric metrics represent a relationship between the baseline and
        delta, and so are true of both or neither. Symmetric metrics are
        only tracked on using baseline variable. An example is "change in
        top three results".
    """

    __metaclass__ = ABCMeta

    def __init__(self, name, symmetric=False, raw_count=False,
                 printset="random", printnum=20,
                 symbols=["&Delta;", "&Delta;"]):
        self.name = name
        self.symmetric = symmetric
        self.printset = printset
        self.printnum = printnum
        self.symbols = symbols
        self.b2d_diff = []
        self.d2b_diff = []
        self.raw_count = raw_count
        self.total_queries = 0
        self.baseline_count = 0
        self.delta_count = 0

    def measure(self, baseline, delta, index):
        """Compares baseline json object to delta json object and
           determines whether the metric criteria are met, then does
           appropriate bookkeeping. index serves as an id for the pair
           being compared.
        """
        self.total_queries += 1  # processed another one

        baseline_is = False  # does baseline qualify?
        delta_is = False     # does delta qualify?

        if self.has_condition(baseline, delta):
            baseline_is = True
            self.baseline_count += 1

        if not self.symmetric and self.has_condition(delta, baseline):
            delta_is = True
            self.delta_count += 1

        if baseline_is and not delta_is:
            self.add_diff(baseline, delta, index)

        if not self.symmetric and not baseline_is and delta_is:
            self.add_diff(baseline, delta, index, delta=True)

    def add_diff(self, b, d, index, delta=False):
        """Add example diff to b2d_diff (delta=False) or d2b_diff (delta=True)
        """

        query_string = b_query = d_query = ""

        if "query" in b:
            b_query = b["query"]
        if "query" in d:
            d_query = d["query"]

        if b_query == d_query:
            query_string = b_query
        else:
            query_string = u"{} / {}".format(b_query, d_query)

        if query_string == "":
            query_string = "[no-query-string]"

        if delta:
            self.d2b_diff.append([index, query_string])
        else:
            self.b2d_diff.append([index, query_string])

    def results(self, what="diff"):
        """Returns a string with the metric results
            what: "baseline", "delta", or "diff", generates appropriate summary
        """

        if what == "baseline" or what == "delta":
            if what == "delta" and self.symmetric:
                what = "baseline"
            ret_string = "&nbsp;&nbsp; "
            count = self.baseline_count if what == "baseline" else self.delta_count
            diffstr = ""
            if what == "delta":
                diff = self.delta_count - self.baseline_count
                if diff != 0:
                    diffstr = " ({}{}" if self.raw_count else " ({}{:.1f}"
                    if not self.raw_count:
                        diff *= 100/float(self.total_queries)
                        diffstr += "%"
                    diffstr += ")"
                    plus = "+" if diff > 0 else ""
                    diffstr = diffstr.format(plus, diff)
            if self.raw_count:
                ret_string += "<b>{}:</b> {}{}".format(self.name, count, diffstr)
            else:
                ret_string += "<b>{}:</b> {:.1f}%{}".format(
                    self.name, 100*count/float(self.total_queries), diffstr
                    )
            return ret_string + "<br>\n"

        elif self.printnum > 0:  # diff
            ret_string = "<b>{}:</b><br>\n".format(self.name)
            printed = 0
            if self.printset == "random":
                # shuffle, unless all will be printed, then don't bother
                if (len(self.b2d_diff) > self.printnum):
                    shuffle(self.b2d_diff)
                if (len(self.d2b_diff) > self.printnum):
                    shuffle(self.d2b_diff)
            for ex in self.b2d_diff:
                ret_string += \
                    u"&nbsp;&nbsp;{} <a href='diffs/diff{}.html'>{}</a><br>\n".format(
                        self.symbols[0], ex[0], ex[1]
                        )
                printed += 1
                if printed >= self.printnum:
                    break
            if not self.symmetric:
                ret_string += "<br>\n"
                printed = 0
                for ex in self.d2b_diff:
                    ret_string += \
                        u"&nbsp;&nbsp;{} <a href='diffs/diff{}.html'>{}</a><br>\n".format(
                            self.symbols[1], ex[0], ex[1]
                            )
                    printed += 1
                    if printed >= self.printnum:
                        break
            return ret_string + "<br>\n"

        return ""

    @abstractmethod
    def has_condition(self, x, y):
        """Return true or false on whether the condition of the metric is satisfied."""
        pass


class ZeroResultsRate(Metric):
    """Percentage of queries that return zero results."""

    __metaclass__ = ABCMeta

    def __init__(self):
        super(ZeroResultsRate, self).__init__("Zero Results",
                                              symbols=["&darr;", "&uarr;"])

    def has_condition(self, x, y):
        """Simple check: is totalHits == 0?
        """
        if "totalHits" in x:
            return x["totalHits"] == 0
        return 1  # empty JSON mean no hits


class TopNDiff(Metric):
    """Percentage of query pairs where the top N results DO NOT have the
       same pageIds (ignoring order by default)
    """

    __metaclass__ = ABCMeta

    def __init__(self, topN=5, sorted=False):
        sortstr = "Sorted" if sorted else "Unsorted"
        self.sorted = sorted
        self.topN = topN
        super(TopNDiff, self).__init__("Top {} {} Results Differ".format(topN, sortstr),
                                       symmetric=True)

    def has_condition(self, x, y):
        if "totalHits" in x:
            x_hits = x["totalHits"]
        else:
            x_hits = 0
        if "totalHits" in y:
            y_hits = y["totalHits"]
        else:
            y_hits = 0

        if x_hits == 0 and y_hits == 0:
            return 0  # no hits means no diff

        x_ids = map((lambda r: r["pageId"]), x["rows"][0:self.topN])
        y_ids = map((lambda r: r["pageId"]), y["rows"][0:self.topN])

        if len(x_ids) != len(y_ids):
            return 1

        if self.sorted:
            if x_ids == y_ids:
                return 0
        else:
            if set(x_ids) == set(y_ids):
                return 0

        return 1


class QueryCount(Metric):
    """A count of queries in this query set."""

    __metaclass__ = ABCMeta

    def __init__(self):
        super(QueryCount, self).__init__("Query Count", raw_count=True, printnum=0)

    def has_condition(self, x, y):
        return not len(x) == 0


def print_report(target_dir, diff_count, file1, file2, myMetrics):
    report_file = open(target_dir + "report.html", "w")
    report_file.write(textwrap.dedent("""\
        <h2>Comparison run summary: {}</h2>
        <blockquote>
        <b>Stats:</b> {} query pairs compared<br>
        </blockquote>

        <h3>Baseline: {}</h3>
        <blockquote>
        <b>Metrics:</b><br>
        """).format(target_dir, diff_count, file1))

    for m in myMetrics:
        report_file.write(m.results("baseline").encode('ascii', 'xmlcharrefreplace'))

    report_file.write(textwrap.dedent("""\
        </blockquote>

        <h3>Delta: {}</h3>
        <blockquote>
        <b>Metrics:</b><br>
        """).format(file2))

    for m in myMetrics:
        report_file.write(m.results("delta").encode('ascii', 'xmlcharrefreplace'))

    report_file.write(textwrap.dedent("""\
        </blockquote>

        <h3>Diffs</h3>
        <blockquote>
        """))

    for m in myMetrics:
        report_file.write(m.results().encode('ascii', 'xmlcharrefreplace'))

    report_file.write("</blockquote>")


def main():
    parser = argparse.ArgumentParser(
        description="Generate a report comparing two relevance lab query runs",
        prog=sys.argv[0]
        )
    parser.add_argument("file", nargs=2, help="files to diff")
    parser.add_argument("-d", "--dir", dest="dir", default="./comp/",
                        help="output directory, default is ./comp/")
    args = parser.parse_args()

    (file1, file2) = args.file
    target_dir = args.dir + "/"

    if not os.path.exists(target_dir):
        os.makedirs(os.path.dirname(target_dir))

    diff_count = 0

    # set up metrics
    myMetrics = [
        QueryCount(),
        ZeroResultsRate(),
        TopNDiff(5, sorted=False),
        TopNDiff(5, sorted=True)
        ]

    with open(file1) as a, open(file2) as b:
        for tuple in izip_longest(a, b, fillvalue="{}"):
            (aline, bline) = tuple
            aline = aline.strip(" \t\n")
            bline = bline.strip(" \t\n")
            if aline == "":
                aline = "{}"
            if bline == "":
                bline = "{}"
            ajson = json.loads(aline)
            bjson = json.loads(bline)

            diff_count += 1
            for m in myMetrics:
                m.measure(ajson, bjson, diff_count)

    print_report(target_dir, diff_count, file1, file2, myMetrics)


if __name__ == "__main__":
    main()
