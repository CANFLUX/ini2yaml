import re
import os
import sys
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedSeq
from ruamel.yaml.scalarstring import PlainScalarString, LiteralScalarString
from ruamel.yaml.scalarint import ScalarInt
from ruamel.yaml.scalarfloat import ScalarFloat
from ruamel.yaml.scalarbool import ScalarBoolean
from datetime import datetime,timedelta
from dateutil.parser import parse as dateparse
from dataclasses import dataclass,field
from helperFunctions import asdict_repr

yaml = YAML()

@dataclass(kw_only=True)
class yml_base:
    metadata: dict = field(default_factory=dict)
    globalVars: dict = field(default_factory=dict)
    Trace: dict = field(default_factory=dict)
    Include: dict = field(default_factory=dict)

@dataclass(kw_only=True)
class iniFile:
    verbose: bool = True
    ini_path: str = None
    ini_string: str = None

    def __post_init__(self):
        if os.path.isfile(self.ini_path):
            if self.verbose:
                print(self.ini_path)
            with open(self.ini_path) as f:
                self.ini_string = f.read()


@dataclass(kw_only=True)
class Trace:
    # The expected fields and their corresponding types for a trace object
    # Required for all 
    variableName: str = field(default='', metadata={'standard':True,'stage':'common','literal':False})
    title: str = field(default='', metadata={'standard':True,'stage':'common','literal':False})
    units: str = field(default='', metadata={'standard':True,'stage':'common','literal':False})
    # Required for first stage
    inputFileName: list = field(default_factory=list, metadata={'standard':True,'stage':'firststage','literal':False})
    instrumentType: str = field(default='', metadata={'standard':True,'stage':'firststage','literal':False})
    measurementType: str = field(default='', metadata={'standard':True,'stage':'firststage','literal':False})
    minMax: list = field(default_factory=list, metadata={'standard':True,'stage':'firststage','literal':False})
    # Required for second stage
    Evaluate: str = field(default='', metadata={'standard':True,'stage':'secondstage','literal':True})
    postEvaluate: str = field(default='', metadata={'standard':True,'stage':'secondstage optional','literal':True})
    # Optional parameters
    # ONLY required for optionals we want to have predefined settings
    # Can take any non-defined field, but defining here will give defaults for standardization
    Overwrite: int = field(default=0, metadata={'standard':True,'stage':'firststage','literal':False})
    dependent: list = field(default_factory=list, metadata={'standard':True,'stage':'firststage optional','literal':False})
    # Hidden (parameters to control behaviour which will not be written)
    # by default, repr should be true, but when setting globals trace-by-trace, will set to false
    repr: bool = field(default=True,repr=False,metadata={'standard':True,'stage':None,'literal':False})
    stage: str = field(default='firststage',repr=False,metadata={'standard':True,'stage':None,'literal':False})
    fields_on_the_fly: bool = field(default=False,repr=False,metadata={'standard':True,'stage':None,'literal':False})
    verbose: bool = field(default=False,repr=False,metadata={'standard':True,'stage':None,'literal':False})

    def __post_init__(self):
                # A bit hack-key, remove appended fields from previous instance
        # adding fields on the fly ensure the non-standard keys are transferred to the new yaml files
        if self.fields_on_the_fly:
            flds = list(self.__dataclass_fields__.keys())
            for k in flds:
                if not self.__dataclass_fields__[k].metadata['standard']:
                    self.__dataclass_fields__.pop(k)
        # Set repr to true if current stage or common field
        # Set to default to false otherwise
        # If provided, will set repr = True
        for k,v in self.__dataclass_fields__.items():
            if v.metadata['stage'] in [self.stage,'common']:
                self.__dataclass_fields__[k].repr=True
            else:
                self.__dataclass_fields__[k].repr=False
    
    def new_field(self,name,type,literal=False):
        metadata = {'standard':False,'stage':self.stage,'literal':literal}
        if type is str:
            self.__dataclass_fields__[name] = field(default='',metadata=metadata,repr=True)
            self.__dataclass_fields__[name].name = name
            self.__dataclass_fields__[name].type = type
            
        elif type is list or type is set:
            self.__dataclass_fields__[name] = field(default_factory=type,metadata=metadata,repr=True)
            self.__dataclass_fields__[name].name = name
            self.__dataclass_fields__[name].type = type
        else:
            self.__dataclass_fields__[name] = field(default=None,metadata=metadata,repr=True)
            self.__dataclass_fields__[name].name = name
            self.__dataclass_fields__[name].type = type

        if self.verbose: print('Added: \n',self.__dataclass_fields__[name])

    def add_item(self,key=None,text=None,anchors=None):
        Inf = float('inf')
        NaN = float('NaN')
        nan = float('NaN')
        if text.startswith("'") and (not text.startswith("'[") or 'Evaluate' in key):
            if key not in self.__dataclass_fields__:
                self.new_field(key,str)
            if self.__dataclass_fields__[key].metadata['literal']:
                text = CleanedText(text=text,forPython=False,PreserveComments=True).text
                self.__dict__[key] = LiteralScalarString(text)
            else:
                text = CleanedText(text=text,forPython=False).text
                self.__dict__[key] = PlainScalarString(text)
        elif not text.startswith("'") or (text.startswith("'[") and not 'Evaluate' in key):
            text = CleanedText(text=text,forPython=True).text
            if 'globalVars' in text:
                refs = re.findall(r'(globalVars(\.\w+)+)',text)
                for j in range(len(refs)):
                    text = text.replace(refs[j][0],f"anchors[1]['{refs[j][0]}']")
                
            text = eval(text)
            if type(text) is set:
                text = list(text)
            if key not in self.__dataclass_fields__:
                self.new_field(key,type(text))
            if type(text) is list:
                self.__dict__[key] = CommentedSeq(text)
            elif type(text) is int:
                self.__dict__[key] = ScalarInt(text)
            elif type(text) is float:
                self.__dict__[key] = ScalarFloat(text)
            elif type(text) is bool:
                self.__dict__[key] = ScalarBoolean(text)
            elif 'ruamel.yaml' in str(type(text)):
                self.__dict__[key] = text
            else:
                breakpoint()
                sys.exit(f"Add {type(text)} for {key}")

        if anchors is not None:
            self.__dict__[key].yaml_set_anchor(anchors[0])

        self.__dataclass_fields__[key].repr = True
    
    def from_trace_block(self,ini_string):
        # parse the trace from an ini file
        # Define python versions of matlab keywords
        lb_key = '~linebreak~'
        new_string = ''
        pattern = r"'(.*?)'"
        def lb_replacer(match):
            return(match[0].replace('\n',lb_key))
        new_string = re.sub(pattern,lb_replacer,ini_string, flags=re.DOTALL)
        key_val_pairs = {l.split('=',1)[0].strip():l.split('=',1)[-1].strip().replace(lb_key,'\n')
                        for l in new_string.split('\n') 
                        if '=' in l and not l.strip().startswith('%') and not l.strip().startswith(';')}
        
        # Autodetect type, if it starts with single quote its a string literal, except when list (followed by a bracket) not starting evaluate
        for key,text in key_val_pairs.items():
            self.add_item(key=key,text=text)

@dataclass(kw_only=True)
class parser:
    root: str
    SiteID: str = None
    stage: str = None
    include: str = None
    verbose: bool = True
    base_prop_by_stage: dict = field(default_factory=lambda:{
        'firststage':['SiteID','Site_name','Difference_GMT_to_local_time','Timezone'],
        'secondstage':['SiteID','Site_name','input_path','output_path','high_level_path','searchPath']
    })
    fields_on_the_fly: bool = False # If true, will allow non-standard fields which are not declared explicitly in Trace class

    def __post_init__(self):
        self.config = yml_base()
        if self.SiteID is not None:
            fname = os.path.join(self.root,self.SiteID,f'{self.SiteID}_{self.stage}.ini')
        else:
            fname = os.path.join(self.root,self.include)
        if os.path.isfile(fname):
            with open(fname,encoding='utf-8') as f:
                print('reading ',fname)
                self.ini_string = f.read()
        else:
            sys.exit('Not a file: '+fname)
        
        self.parse_traces()
        self.parse_metadata()
        self.parse_globals()
        self.parse_includes()

        if not self.include:
            self.config.Include = list(self.config.Include.keys())
            
        outpath = os.path.join(self.root,fname.replace('.ini','.yml'))
        self.write(outpath)
      
    def parse_traces(self):
        # Find trace blocks
        pattern = r"\[Trace\](.*?)\[End\]"
        matches = re.findall(pattern, self.ini_string, flags=re.DOTALL)
        self.trace_blocks = []
        for match in matches:
            if self.include is None: overwrite = 0
            else: overwrite = 1   
            trace = Trace(Overwrite=overwrite,stage=self.stage,fields_on_the_fly=self.fields_on_the_fly,verbose=self.verbose)             
            trace.from_trace_block(match)
            if trace.variableName != '':
                # Custom function to dump dataclass to dict conditional upon each field.repr parameter
                self.config.Trace[trace.variableName] = asdict_repr.asdict_repr(trace)
            self.ini_string = self.ini_string.replace(f'[Trace]{match}[End]','')
        self.ini_string = self.ini_string.strip()
    
    def parse_metadata(self):
        mdLines = [l for l in self.ini_string.split('\n') 
                    if '=' in l and len(l.strip()) and
                    not l.strip().startswith('%') and
                    not l.strip().startswith(';') and
                    'globalVars' not in l]
        metadata = {}
        for l in mdLines:
            metadata[l.split('=',1)[0].strip()] = l.split('=',1)[-1].strip() 
            self.ini_string = self.ini_string.replace(l,'')
        temp = Trace(stage=None,fields_on_the_fly=True)
        for key,text in metadata.items():
            temp.add_item(key=key,text=text)
            self.config.metadata[key] = temp.__dict__[key]

    def parse_includes(self):
        # Call self recursively to parse each include file
        if '#include' in self.ini_string:
            includes = [line for line in self.ini_string.splitlines() if line.startswith('#include')]
            for include in includes:
                fname = include.split('#include')[-1].strip()
                self.config.Include[fname.split('.')[0]] = parser(root=self.root,include=fname,stage=self.stage,verbose=self.verbose).config.Trace
                # Remove lines which have been processed
                self.ini_string = self.ini_string.replace(include,' ')

    def parse_globals(self):
        # extract globalVars
        globalTemp = [l for l in self.ini_string.split('\n') if l.startswith('globalVars')]
        # For tracking Trace objects
        globalVars = {}
        # For writing to self.config
        globalDump = {}
        anchors = {}
        name = None
        for gVar in globalTemp:
            self.ini_string = self.ini_string.replace(gVar,'')
            gVar = [g.strip() for g in gVar.split('=',1)]
            key = gVar[0].split('.')
            text = gVar[-1]
            if len(key) == 4:
                if key[1] not in globalVars:
                    globalVars[key[1]] = {}
                    globalDump[key[1]] = {}
                if key[2] not in globalVars[key[1]]:
                    globalVars[key[1]][key[2]] = Trace(variableName=key[2],Overwrite=1,stage=None,fields_on_the_fly=True,repr=False)
                    globalDump[key[1]][key[2]] = {}
                globalVars[key[1]][key[2]].add_item(
                    key=key[3],text=text,
                    anchors=[gVar[0].replace('.','__'),anchors])
                anchors[gVar[0]] = globalVars[key[1]][key[2]].__dict__[key[3]]
                globalDump[key[1]][key[2]][key[3]] = globalVars[key[1]][key[2]].__dict__[key[3]]
            elif len(key) == 3:
                if key[1] not in globalVars:
                    globalVars[key[1]] = Trace(variableName=key[1],Overwrite=1,stage=None,fields_on_the_fly=True,repr=False)
                    globalDump[key[1]] = {}
                globalVars[key[1]].add_item(
                    key=key[2],text=text,
                    anchors=[gVar[0].replace('.','__'),anchors])
                anchors[gVar[0]] = globalVars[key[1]].__dict__[key[2]]
                globalDump[key[1]][key[2]] = globalVars[key[1]].__dict__[key[2]]
            elif len(key) == 2:
                if key[1] not in globalVars:
                    globalVars[key[1]] = Trace(variableName=key[1],Overwrite=1,stage=None,fields_on_the_fly=True,repr=False)
                    globalVars[key[1]].add_item(
                        key=key[1],text=text,
                        anchors=[gVar[0].replace('.','__'),anchors])
                    anchors[gVar[0]] = globalVars[key[1]].__dict__[key[1]]
                    globalDump[key[1]] = globalVars[key[1]].__dict__[key[1]]
        self.config.globalVars = globalDump

    def write(self,outpath):
        print('Writing ',outpath)
        with open(outpath,'w+',encoding="utf-8") as f:
            try:
                yaml.dump(self.config.__dict__,f)
            except:
                breakpoint()
        self.cleanKeys(outpath)
    
    def cleanKeys(self,outpath):
        # Hardcoded custom translations for now
        # Can give more nuanced approach later if it becomes necessary
        patterns = {'Difference_GMT_to_local_time':'Diff_GMT_to_local_time'}
        with open(outpath) as f:
            ymlstring = f.read()
        for k,v in patterns.items():
            ymlstring = ymlstring.replace(k,v)
        with open(outpath,'w+') as f:
            f.write(ymlstring)

@dataclass(kw_only=True)
class CleanedText:
    text: str
    forPython: bool
    PreserveComments: bool = False
    bp: bool = False
    
    def __post_init__(self):
        if not self.forPython:
            self.clean_for_string_formatting()
        else:
            self.clean_for_python_parsing()
    
    def clean_for_string_formatting(self):
        if not self.PreserveComments:
            # Exclude comments, but preserve percent signs within strings
            pattern = r"(\"[^\"]*\"|'[^']*')|%(.*)"
            def replacer(match):
                if match.group(1):  # quoted string
                    return match.group(1)
                else:               # bare %
                    return ''
            if self.text != '%':
                self.text = re.sub(pattern, replacer, self.text)
        
        self.text = self.text.strip()
        if self.text != "''":
            self.text = self.text.replace("''",'"')
        self.text = self.text.replace("'",'')
        self.text = self.text.replace('\t','')


    def clean_for_python_parsing(self):
        if self.bp: breakpoint()
        # Exclude comments, but preserve percent signs within strings
        pattern = r"(\"[^\"]*\"|'[^']*')|%(.*)"
        def replacer(match):
            if match.group(1):  # quoted string
                return match.group(1)
            else:               # bare %
                return ''
        self.text = re.sub(pattern, replacer, self.text)
        # Delete blank lines
        if '\n' in self.text:
            breakpoint()
        self.text = '\n'.join([l.strip() for l in self.text.split('\n') if len(l.strip()) and not l.strip().startswith(';')])
        # Convert set notation to list notation
        self.text = self.text.replace('{','[').replace('}',']')
        # Replace functions names which are directly translatable to python
        self.text = self.replace_num2str(text=self.text)
        # Convert to standard pythonic dates
        self.text = self.replace_datenum(text=self.text) 
        # Add commas to space delimited lists 
        self.text = self.format_lists(text=self.text)    
        # Ensure all equal signs have space on each side
        self.text = self.text.replace('=',' = ')
        # Add spaces before/after brackets to make parsing simpler
        self.text = self.text.replace('[',' [ ').replace(']',' ] ')
        # Except for start/end blocks
        self.text = self.text.replace(' [ End ] ','[End]').replace(' [ Trace ] ','[Trace]')
        # Strip extra spaces
        self.text = self.text.strip()    

    def replace_num2str(self,text):
        # Exclude comments, but preserve percent signs within strings
        pattern = r'\s*num2str\((.*?)\)\s*'
        def replacer(match):
            inner = match.group(1) 
            return (f" {inner} ")
        return(re.sub(pattern, replacer, text))

    def replace_datenum(self,text):
        # Replace all depreciated datenum objects with datetime object which is valid in both python and matlab
        # write a wrapper to go from datetime to depreciated datenum in matlab
        pattern = r'datenum\((.*?)\)'  # capture inside quotes
        def get_date(m):
            inner = m.group(1)
            if inner.startswith('"') or inner.startswith("'"):
                inner = inner.strip('"').strip("'")
                if '24:00' in inner:
                    inner = inner.replace('24:00','23:59')
                    d = dateparse(inner)+timedelta(minutes=1)
                else:
                    d = dateparse(inner)
            else:
                inner = ','.join(str(int(i)) for i in inner.split(','))
                d = eval('datetime('+inner+')')
            # format datestring, ~_~ is a stand in for a space to be replaced after list formatting
            d = d.strftime("%Y-%m-%dT%H:%M:%S")
            return(f'"{d}"')
        return(re.sub(pattern,get_date,text))
        
    def format_lists(self,text):
        # need to format correctly for parsing to python
        # matlab allows list to be delimited by spaces, python requires commas
        # matlab dimensions are denoted by semicolons, python uses nested brackets
        pattern = r"\[(.*?)\]"
        def replace_spaces_and_semicolons(m):
            inner = m.group(1)
            inner = re.sub(r"'\s*&\s*'*","'&'",inner.strip())
            inner = re.sub(r'(?<=[^,;])\s+(?=[^,])',' , ',inner).replace("'&'","' & '")
            if inner.count(';'):
                inner = [inn for inn in inner.split(';') if len(inn.strip())>0]
                if len(inner)==1:
                    inner = inner[0]
                else:
                    inner ='['+('],['.join(inner))+']'
            return (f'[{inner}]')
        fmtd = re.sub(pattern,replace_spaces_and_semicolons,text)
        # Get rid of quoted lists if they exist
        def replace_quotes(m):
            return(f'[{m.group(1)}]')
        pattern = r"'\[(.*?)\]'"
        fmtd = re.sub(pattern,replace_quotes,fmtd)
        pattern = r"'\[(.*?)\];'"
        fmtd = re.sub(pattern,replace_quotes,fmtd)
        # convert {[..]} to [..]
        pattern = r"{\[(.*?)\]}"
        def clip_brackets(m):
            return('['+m.group(1)+']')
        fmtd = re.sub(pattern,clip_brackets,fmtd)
        return(fmtd)
