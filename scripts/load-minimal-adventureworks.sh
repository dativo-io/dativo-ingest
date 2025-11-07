#!/bin/bash
# Load minimal AdventureWorks data for smoke tests
# This creates the essential tables with sample data

set -e

echo "Loading minimal AdventureWorks data for smoke tests..."

docker exec -i dativo-postgres psql -U postgres -d Adventureworks <<EOF

-- Create schemas
CREATE SCHEMA IF NOT EXISTS person;
CREATE SCHEMA IF NOT EXISTS production;
CREATE SCHEMA IF NOT EXISTS sales;
CREATE SCHEMA IF NOT EXISTS humanresources;
CREATE SCHEMA IF NOT EXISTS purchasing;

-- Person.Person table
CREATE TABLE IF NOT EXISTS person.person (
    businessentityid INTEGER PRIMARY KEY,
    persontype VARCHAR(2),
    namestyle BOOLEAN,
    title VARCHAR(8),
    firstname VARCHAR(50),
    middlename VARCHAR(50),
    lastname VARCHAR(50),
    suffix VARCHAR(10),
    emailpromotion INTEGER,
    additionalcontactinfo TEXT,
    demographics TEXT,
    rowguid UUID,
    modifieddate TIMESTAMP
);

INSERT INTO person.person (businessentityid, persontype, namestyle, firstname, lastname, emailpromotion, modifieddate) VALUES
(1, 'EM', false, 'Ken', 'Sánchez', 0, '2009-01-07 00:00:00'),
(2, 'SC', false, 'Terri', 'Duffy', 1, '2008-01-24 00:00:00'),
(3, 'EM', false, 'Roberto', 'Tamburello', 0, '2007-11-04 00:00:00'),
(4, 'EM', false, 'Rob', 'Walters', 0, '2007-11-28 00:00:00'),
(5, 'EM', false, 'Gail', 'Erickson', 0, '2007-12-30 00:00:00')
ON CONFLICT (businessentityid) DO NOTHING;

-- Production.Product table
CREATE TABLE IF NOT EXISTS production.product (
    productid INTEGER PRIMARY KEY,
    name VARCHAR(100),
    productnumber VARCHAR(25),
    makeflag BOOLEAN,
    finishedgoodsflag BOOLEAN,
    color VARCHAR(15),
    safetystocklevel SMALLINT,
    reorderpoint SMALLINT,
    standardcost NUMERIC,
    listprice NUMERIC,
    size VARCHAR(5),
    sizeunitmeasurecode VARCHAR(3),
    weightunitmeasurecode VARCHAR(3),
    weight NUMERIC,
    daystomanufacture INTEGER,
    productline VARCHAR(2),
    class VARCHAR(2),
    style VARCHAR(2),
    productsubcategoryid INTEGER,
    productmodelid INTEGER,
    sellstartdate TIMESTAMP,
    sellenddate TIMESTAMP,
    discontinueddate TIMESTAMP,
    rowguid UUID,
    modifieddate TIMESTAMP
);

INSERT INTO production.product (productid, name, productnumber, makeflag, finishedgoodsflag, safetystocklevel, reorderpoint, standardcost, listprice, sellstartdate, modifieddate) VALUES
(1, 'Adjustable Race', 'AR-5381', false, true, 750, 375, 0.00, 0.00, '2008-04-30 00:00:00', '2008-04-30 00:00:00'),
(2, 'Bearing Ball', 'BB-7421', false, true, 800, 400, 0.00, 0.00, '2008-04-30 00:00:00', '2008-04-30 00:00:00'),
(3, 'BB Ball Bearing', 'BE-2349', true, false, 1000, 500, 0.00, 0.00, '2008-04-30 00:00:00', '2008-04-30 00:00:00'),
(4, 'Headset Ball Bearings', 'BE-2908', false, true, 750, 375, 0.00, 0.00, '2008-04-30 00:00:00', '2008-04-30 00:00:00'),
(5, 'Blade', 'BL-2036', true, false, 800, 400, 0.00, 0.00, '2008-04-30 00:00:00', '2008-04-30 00:00:00')
ON CONFLICT (productid) DO NOTHING;

-- Sales.Customer table
CREATE TABLE IF NOT EXISTS sales.customer (
    customerid INTEGER PRIMARY KEY,
    personid INTEGER,
    storeid INTEGER,
    territoryid INTEGER,
    accountnumber VARCHAR(10),
    rowguid UUID,
    modifieddate TIMESTAMP
);

INSERT INTO sales.customer (customerid, personid, storeid, territoryid, accountnumber, modifieddate) VALUES
(1, 1, NULL, 1, 'AW00000001', '2007-12-19 00:00:00'),
(2, 2, NULL, 1, 'AW00000002', '2007-12-19 00:00:00'),
(3, 3, NULL, 1, 'AW00000003', '2007-12-19 00:00:00'),
(4, 4, NULL, 1, 'AW00000004', '2007-12-19 00:00:00'),
(5, 5, NULL, 1, 'AW00000005', '2007-12-19 00:00:00')
ON CONFLICT (customerid) DO NOTHING;

-- Sales.SalesOrderHeader table
CREATE TABLE IF NOT EXISTS sales.salesorderheader (
    salesorderid INTEGER PRIMARY KEY,
    revisionnumber SMALLINT,
    orderdate TIMESTAMP,
    duedate TIMESTAMP,
    shipdate TIMESTAMP,
    status SMALLINT,
    onlineorderflag BOOLEAN,
    purchaseordernumber VARCHAR(25),
    accountnumber VARCHAR(15),
    customerid INTEGER,
    salespersonid INTEGER,
    territoryid INTEGER,
    billtoaddressid INTEGER,
    shiptoaddressid INTEGER,
    shipmethodid INTEGER,
    creditcardid INTEGER,
    creditcardapprovalcode VARCHAR(15),
    currencyrateid INTEGER,
    subtotal NUMERIC,
    taxamt NUMERIC,
    freight NUMERIC,
    totaldue NUMERIC,
    comment TEXT,
    rowguid UUID,
    modifieddate TIMESTAMP
);

INSERT INTO sales.salesorderheader (salesorderid, revisionnumber, orderdate, duedate, shipdate, status, onlineorderflag, customerid, subtotal, taxamt, freight, totaldue, modifieddate) VALUES
(43659, 8, '2011-05-31 00:00:00', '2011-06-12 00:00:00', '2011-06-07 00:00:00', 5, true, 29825, 1294.2529, 124.2483, 38.8276, 1457.3288, '2011-06-07 00:00:00'),
(43660, 8, '2011-05-31 00:00:00', '2011-06-12 00:00:00', '2011-06-07 00:00:00', 5, true, 29672, 32726.4786, 3141.7419, 982.1943, 36850.4148, '2011-06-07 00:00:00'),
(43661, 8, '2011-05-31 00:00:00', '2011-06-12 00:00:00', '2011-06-07 00:00:00', 5, true, 29734, 28832.5289, 2767.9228, 864.9759, 32465.4276, '2011-06-07 00:00:00')
ON CONFLICT (salesorderid) DO NOTHING;

-- HumanResources.Employee table
CREATE TABLE IF NOT EXISTS humanresources.employee (
    businessentityid INTEGER PRIMARY KEY,
    nationalidnumber VARCHAR(15),
    loginid VARCHAR(256),
    organizationnode VARCHAR(255),
    organizationlevel SMALLINT,
    jobtitle VARCHAR(50),
    birthdate DATE,
    maritalstatus VARCHAR(1),
    gender VARCHAR(1),
    hiredate DATE,
    salariedflag BOOLEAN,
    vacationhours SMALLINT,
    sickleavehours SMALLINT,
    currentflag BOOLEAN,
    rowguid UUID,
    modifieddate TIMESTAMP
);

INSERT INTO humanresources.employee (businessentityid, nationalidnumber, loginid, jobtitle, birthdate, maritalstatus, gender, hiredate, salariedflag, vacationhours, sickleavehours, currentflag, modifieddate) VALUES
(1, '295847284', 'adventure-works\ken0', 'Chief Executive Officer', '1969-01-29', 'S', 'M', '2009-01-14', true, 99, 69, true, '2014-06-30 00:00:00'),
(2, '245797967', 'adventure-works\terri0', 'Vice President of Engineering', '1971-08-01', 'S', 'F', '2008-01-31', true, 1, 20, true, '2014-06-30 00:00:00'),
(3, '509647174', 'adventure-works\roberto0', 'Engineering Manager', '1974-11-12', 'M', 'M', '2007-11-11', true, 2, 21, true, '2014-06-30 00:00:00')
ON CONFLICT (businessentityid) DO NOTHING;

-- Person.Address table
CREATE TABLE IF NOT EXISTS person.address (
    addressid INTEGER PRIMARY KEY,
    addressline1 VARCHAR(60),
    addressline2 VARCHAR(60),
    city VARCHAR(30),
    stateprovinceid INTEGER,
    postalcode VARCHAR(15),
    spatiallocation TEXT,
    rowguid UUID,
    modifieddate TIMESTAMP
);

INSERT INTO person.address (addressid, addressline1, city, stateprovinceid, postalcode, modifieddate) VALUES
(1, '1970 Napa Ct.', 'Bothell', 79, '98011', '2007-12-19 00:00:00'),
(2, '9833 Mt. Dias Blv.', 'Bothell', 79, '98011', '2007-12-19 00:00:00'),
(3, '7484 Roundtree Drive', 'Bothell', 79, '98011', '2007-12-19 00:00:00'),
(4, '9539 Glenside Dr', 'Bothell', 79, '98011', '2007-12-19 00:00:00'),
(5, '1226 Shoe St.', 'Bothell', 79, '98011', '2007-12-19 00:00:00')
ON CONFLICT (addressid) DO NOTHING;

-- Production.ProductCategory table
CREATE TABLE IF NOT EXISTS production.productcategory (
    productcategoryid INTEGER PRIMARY KEY,
    name VARCHAR(50),
    rowguid UUID,
    modifieddate TIMESTAMP
);

INSERT INTO production.productcategory (productcategoryid, name, modifieddate) VALUES
(1, 'Bikes', '2007-12-19 00:00:00'),
(2, 'Components', '2007-12-19 00:00:00'),
(3, 'Clothing', '2007-12-19 00:00:00'),
(4, 'Accessories', '2007-12-19 00:00:00')
ON CONFLICT (productcategoryid) DO NOTHING;

EOF

echo "Minimal AdventureWorks data loaded successfully!"
echo ""
echo "Tables created with sample data:"
echo "  - person.person (5 rows)"
echo "  - production.product (5 rows)"
echo "  - sales.customer (5 rows)"
echo "  - sales.salesorderheader (3 rows)"
echo "  - humanresources.employee (3 rows)"
echo "  - person.address (5 rows)"
echo "  - production.productcategory (4 rows)"

