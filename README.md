# BaseApp Backend

This repository contains baseapp django packages to be reused accross projects based on TSL's BaseApp

## [baseapp-core](baseapp-core)

The core contains the basics for BaseApp like Django Rest Framework's basic setup, custom ModelSerializer and fields, also base email template, testing helpers and other utilities.

## [baseapp-auth](baseapp-auth)

Reusable user and authentication utilities. Authentication setup using SimpleToken, JWT and Multi-factor authentication (MFA)

## [baseapp-reactions](baseapp-reactions)

Reusable app to enable User's reactions on any model, features like like/dislike or any other reactions type, customizable for project's needs.

## [baseapp-referrals](baseapp-referrals)

Utilities for user referrals

## [baseapp-drf-view-action-permissions](baseapp-drf-view-action-permissions)

This app uses django provided permission and group model and provides the ability to add roles to a django model, and make views from the [django-restframework](https://www.django-rest-framework.org/) check for them. A **Permission** represents the lowest single unit of access. A **Group** is a collection of Permissions. A **Role** can have many Permision Groups, many Permissions and many **Excluded Permissions**. The access of a Role is the aggregation of its single Permissions + the permissions on its **Permission** Groups - its Excluded Permissions.
