# MetaBaseSync (MBS)

A tool to manage, reuse and automate your sql queries in metabase with a powerful template system (jinja2). 
The cli syntax is inspired by git.

The goal is, that you can pull and push your query definitions from and to metabase from a local directory.

That way you can edit json files and sql queries by hand, keep them under version control like git, keep them better organized, 
reuse queries from and to other projects and make the more dynamic with jinja2 templates.

That way you can also work around some missing features like the not working field filters from nested queries. 
(https://github.com/metabase/metabase/issues/6449)

## Usage

First download the correct executable for your OS. We currently support Linux/Win64, but it should generally build for 
more systems, where a python interpreter is available. 

If you have a python interpreter on your system, you can also do 
<code>pip install git+https://github.com/Administerium/mbs.git </code>. That way it will also create an <code>mbs</code> shortcut in 
your system path, so that mbs is available system-wide.

You can use<code>mbs <command> --help</code>, to get more detailed help to some options.

### First steps

Create an empty directory and run:

    > mbs init https://metabase.example.com               <- replace the URL with your Metabase instance URL
    Created ".mbs" file with url "https://metabase.example.com" in the current directory.

That creates an <code>.mbs</code> file in the current directory, that marks this as a mbs repository for this metabase instance.
Then run in this directory:

    > mbs login Myusername Mypassword
    Login successful.

to log into your instance. The credentials with the session cookie will be saved on your local home directory (Windows: 
<code>C:\Users\<username>\AppData\Local\mbs\mbs\remotes.json</code>, Linux: <code>~/.config/mbs/remotes.json</code>).

Now go into Metabase and add the text snippet <code>## mbs_controlled ##</code> into the sql query as a comment 
(<code>--## mbs_controlled ##</code> in most cases) or in the question description.
This will mark this question as under the control of MBS. Only question (or cards, as they are called in the metabase 
API) with this string are handled by MBS. 

Now pull this cards/questions from metabase to this directory:

    > mbs pull
    Found mbs tag on native sql with id: 100 (test2)
    Created "test2.json".
    Found mbs tag on native sql with id: 116 (test3)
    Created "test3.json".

This will create JSON files, you can edit now. You can also pull a single card with <code>mbs pull <id></code>, 
where you use the card id from the URL in metabase (https://metabase.example.com/question/100-test2 --> id is 100)

After you edited your files and used some cool jinja features (scroll down to read more about them), 
you can push your files back into metabase:

    > mbs push test3.json

You can also push all files at once by not giving a filename, so be careful about that.

Now edit your question/card in Metabase. To configure metabase variables, you have to go into the sql editor and 
delete and add a character on the variable. That way the properties sidebar opens, and you can configure the variable.
After that it would be cool to merge your changes back into your file, right?
So we do just that.

    > mbs merge test3.json

With that we merge everything back, but keep the native SQL part in the file as it is. 
(In fact the only thing kept is the [dataset_query][native][query] value, everything else is overwritten. 
That may get more fine-tuning in the future.) 
You can also merge all files at once by not giving a filename, so be VERY careful about that.

Best practice: Keep your MBS repo under a versioning system like git.

## Jinja2

Jinja2 is a very feature rich templating system. Documentation: https://jinja.palletsprojects.com/en/3.1.x/templates/

### Useful snippets

#### Include another file
```
    ...
    "dataset_query": {
        "database": 7,
        "native": {
            "query": "--## mbs_controlled ##\n{% filter json %}{% include 'my_file_in_include_directory.sql' %}{% endfilter %}",
            "template-tags": {}
        },
        "type": "native"
    },
    ...
```
The <code>{% filter json %}</code> is needed, to escape the SQL file to JSON. You also see, that the mbs tag 
(<code>--## mbs_controlled ##</code>) has to be somewhere: In the included file, just before the 
include statement or in the question's description.

<code>test.sql</code>:
```
SELECT TOP 1000 * FROM mytable
```

#### Give some arguments to the include file
```
    ...
    "dataset_query": {
        "database": 7,
        "native": {
            "query": "{% filter json %}{% with top=10, bananas=20}{% include 'test.sql' %}{% endwith %}{% endfilter %}",
            "template-tags": {}
        },
        "type": "native"
    },
    ...
```
<code>test.sql</code>:
```
--## mbs_version_control
SELECT TOP {{top}} * FROM mytable WHERE mytable.bananas = {{bananas}}
```
#### Hide template parts outside mbs
You can use the variable <code>is_mbs</code> to check in your template for mbs.
```
SELECT TOP 10 * FROM mytable {% if is_mbs %}WHERE mytable.bananas = 0{% endif %}
```
#### Render based on the mbs source filename
You can use the variable <code>mbs_file</code> to get the filename of the currently pushed file with it's relative part inside the repo folder.
With <code>mbs_file_abs</code> you would get the full filesystem path.
```
SELECT TOP 1000 * FROM mytable {% if mbs_file="ten_bananas.json" %}WHERE mytable.bananas = 10{% endif %}
```
#### Escape Metabase variables
Metabase is also using double curly braces, so we have to escape them with <code>{{'{{ my_metabase_var }}'}}</code>.
```
SELECT TOP 1000 * FROM mytable {% if is_mbs %}{{'{{ bananas }}'}}{% endif %}
```

#### Default values

Set some defaults, in case the variables where not set on include.
```
SELECT TOP {{ limit|default(10) }} * FROM mytable
```

## Status

Beta - Contributions are very welcome.

## Building an executable

Tested on Ubuntu 20.04 and Windows 11.

Set up a python 3.8+ venv and run this inside:

    git clone https://github.com/Administerium/mbs.git
    pip install -r requirements.txt
    pyinstaller -y --clean .\mbs.spec

You'll get a mbs executable in the dist folder.

## Use the templates in another project

Mbs is using the render function in a very standard way. If you only render the sql files in your project, you don't 
need to read further, just render them with jinja2.

If you try to use the metabase json files outside metabase, you have to look at this:
There is a special json filter, that escapes sql to include it into a json field.
That speciality is needed, because when you just use <code>json.dumps()</code> with a string, the output has quotes 
around and that's the standard filter behavior. This destroys json syntax highlighting in many editors and is ugly.
So we fix this with this filter:
```
jenv = jinja2.Environment(
    autoescape=False,
    ...  # your other jinja2 options
)
jenv.filters['json'] = lambda a: json.dumps(a)[1:-1]
```
That way your editor better renders the json syntax, when you write it like this:

```
...
    native": {
        "query": "{% filter json %}{% include 'activity.sql' %}{% endfilter %}",
        "template-tags": {}
    },
...
```